"""Đếm những lần máy tự sinh ra bản thu tốt hơn rồi vứt đi.

    python scripts/discarded_cures.py <project...>
    python scripts/discarded_cures.py D:/Novels/Audiobooks/_versions/*/*/

Mẫu cần tìm, mô tả trong [docs/OPTIMISATION_QUEUE.md]:

  bản đương nhiệm  chạm trần khung (`generation_ceiling_hit`) - bộ sinh tự khai nó chạy hết
                   khung mà chưa dừng, tức có tiếng thừa trong file
  một ứng viên     KHÔNG chạm trần, và chỉ trượt bằng mã mà chính sách đã tự xếp vào nhóm
                   "phép kiểm không có ý kiến" (`HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS`)

Khi cả hai đúng, luật giữ-bản-đương-nhiệm giữ lại bản mà bộ sinh chê và ném đi bản mà không
phép kiểm nào chê về *bản thu* - chỉ về việc Whisper đọc được hay không.

Viết file này trước khi sửa, cố ý: một ca đơn lẻ (`"Tiếp theo."` chương 003 alpha.60) không
đủ để đổi một luật đã được ghim bằng test. Nếu mẫu này hiếm thì để nguyên và ghi lại; nếu nó
xảy ra hàng chục lần thì đó là một khoản mất mát đo được, và lúc ấy mới đáng đụng vào.

`generation_ceiling_hit` chỉ được ghi KHI thật sự chạm trần (tts.py), nên khoá vắng mặt nghĩa
là bộ sinh tự kết thúc - đó là điều làm phép đo này chắc chứ không phải suy đoán.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

CEILING = "generation_ceiling_hit"

# Giữ bản sao ở đây thay vì import từ `ebook_reader.pipeline`: script này chạy trên project
# **đã lưu trữ**, và danh sách lúc ấy mới là danh sách đúng để phán xử chúng. Import bản hiện
# tại là lặng lẽ chấm điểm quá khứ bằng luật của hiện tại.
UNINFORMATIVE_AT_TIME_OF_WRITING = frozenset(
    {
        "ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE",
        "ASR_UNVERIFIABLE_SHORT_TEXT",
        "ASR_LOCKED_NAME_ANCHOR_REVIEW",
        "ASR_REPEATED_SHORT_PASS",
        "TTS_SPLIT_RECOVERY",
        "TTS_GENERATION_CEILING_REACHED",
    }
)


# Dưới ngưỡng này ASR không phán xử được, và dự án đã **đo** chứ không đoán: tham chiếu ngắn
# hơn cho tương đồng trung vị 0,27 so với 0,94 của một câu bình thường, trượt ngưỡng 75% số lần
# so với 0,2%. Giữ bản sao ở đây cùng lý do như danh sách trên.
MIN_VERIFIABLE_CHARS_AT_TIME_OF_WRITING = 10

# Mọi mã ASR đều **vô thông tin trên văn bản quá ngắn**, không chỉ những mã trong danh sách
# trên. Đó là chỗ bộ dò đầu tiên quá hẹp: nó đòi mã của ứng viên phải nằm trong
# `UNINFORMATIVE_AT_TIME_OF_WRITING`, nên nó bỏ sót ca `"Bất bại?"` của lô 2 — sáu ký tự
# chữ-số, năm ứng viên, hai trong số đó không chạm trần, tất cả bị xử bằng `ASR_MISMATCH`.
ASR_CODE_PREFIX = "ASR_"


def _too_short_for_asr(text: str | None) -> bool:
    return sum(ch.isalnum() for ch in str(text or "")) < MIN_VERIFIABLE_CHARS_AT_TIME_OF_WRITING


def _hit_ceiling(signal_json: str | None) -> bool:
    try:
        metrics = json.loads(str(signal_json or "{}"))
    except (TypeError, json.JSONDecodeError):
        return False
    return isinstance(metrics, dict) and bool(metrics.get(CEILING))


def _failure_codes(reason: str | None) -> set[str]:
    """`beam=X; greedy=Y; blocking_signal=Z` -> {X, Y}."""
    codes: set[str] = set()
    for part in str(reason or "").split(";"):
        _, _, value = part.partition("=")
        value = value.strip()
        if value and value.isupper():
            codes.add(value)
    return codes


def _scan(project: Path) -> list[dict]:
    database = project / "project.sqlite3"
    if not database.is_file():
        return []
    conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "segment_candidates" not in names:
        return []

    found: list[dict] = []
    for row in conn.execute(
        "SELECT s.id, s.stable_id, s.text, s.status, s.wav_duration, s.signal_json, "
        "ch.title FROM segments s JOIN chapters ch ON ch.id = s.chapter_id "
        "WHERE s.status IN ('failed','warning')"
    ):
        if not _hit_ceiling(row["signal_json"]):
            continue
        rescues = []
        for cand in conn.execute(
            "SELECT repair_round, state, wav_duration, signal_json, failure_reason "
            "FROM segment_candidates WHERE segment_id=? ORDER BY repair_round",
            (row["id"],),
        ):
            if cand["state"] == "promoted" or _hit_ceiling(cand["signal_json"]):
                continue
            codes = _failure_codes(cand["failure_reason"])
            if not codes:
                continue
            # Hai đường vào cùng một kết luận "ứng viên này bị vứt trên bằng chứng vô nghĩa".
            #
            # Đường thứ nhất là bản gốc: mọi mã đều nằm trong danh sách mà chính sách đã tự
            # khai là không mang thông tin.
            #
            # Đường thứ hai thêm sau khi lô 2 lộ ra bộ dò cũ quá hẹp: nếu **văn bản tham chiếu
            # ngắn hơn ngưỡng ASR phán xử được** thì *mọi* mã ASR đều vô thông tin ở đó, kể cả
            # `ASR_MISMATCH`. `"Bất bại?"` có sáu ký tự chữ-số trên ngưỡng mười; năm ứng viên,
            # hai cái không chạm trần, tất cả bị xử bằng `ASR_MISMATCH` — một phép kiểm mà dự
            # án đã đo là trượt 75% số lần ở độ dài ấy.
            uninformative = codes <= UNINFORMATIVE_AT_TIME_OF_WRITING
            asr_only_on_short_text = _too_short_for_asr(row["text"]) and all(
                code.startswith(ASR_CODE_PREFIX) for code in codes
            )
            if uninformative or asr_only_on_short_text:
                rescues.append(
                    {
                        "round": cand["repair_round"],
                        "duration": cand["wav_duration"],
                        "codes": sorted(codes),
                        "why": "vô thông tin" if uninformative else "ASR trên văn bản quá ngắn",
                    }
                )
        if rescues:
            found.append(
                {
                    "chapter": str(row["title"]),
                    "stable_id": str(row["stable_id"]),
                    "text": str(row["text"] or "")[:70],
                    "status": str(row["status"]),
                    "incumbent_duration": row["wav_duration"],
                    "rescues": rescues,
                }
            )
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projects", nargs="+", type=Path)
    parser.add_argument("--quiet", action="store_true", help="chỉ in tổng kết")
    args = parser.parse_args(argv)

    total_segments = total_cases = 0
    for project in args.projects:
        if not (project / "project.sqlite3").is_file():
            continue
        cases = _scan(project)
        conn = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
        n = conn.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
        total_segments += n
        total_cases += len(cases)
        if not cases:
            if not args.quiet:
                print(f"{project.parent.name:32s} 0/{n}")
            continue
        print(f"\n=== {project.parent.name}  ({len(cases)} ca / {n} đoạn)")
        for case in cases:
            print(
                f"  ch{case['chapter']} {case['stable_id']}  "
                f"đương nhiệm {case['incumbent_duration']}s ({case['status']})"
            )
            print(f"     {case['text']!r}")
            for r in case["rescues"]:
                print(
                    f"     vòng {r['round']}: {r['duration']}s, không chạm trần, "
                    f"trượt bằng {','.join(r['codes'])}"
                )

    print()
    print(f"TỔNG: {total_cases} ca trên {total_segments} đoạn đã lưu.")
    if total_segments:
        print(f"      tỉ lệ {total_cases / total_segments * 100:.3f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
