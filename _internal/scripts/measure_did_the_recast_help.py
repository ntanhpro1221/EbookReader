"""Một lượt đúc lại giọng: nó ĐƯA giọng về đa số của sách, hay đẩy đi xa hơn?

    python scripts/measure_did_the_recast_help.py 017 020 047 048 062 082 090

Chỉ đọc. Với mỗi chương, tìm mọi project có nó, xếp theo `book.created_at`, rồi so **hai bản
cuối**: từng người nói, giọng ở bản CŨ và bản MỚI, đối chiếu với **giọng đa số của người ấy trên
cả cuốn sách** (tính từ mọi project, loại chính chương đang xét ra khỏi phép đếm để không tự
chứng minh).

Vì sao cần: ranh giới 4 đúc lại 7 chương và chương 090 ra **xấu hơn** - NATASHA đi từ
`ngoc_linh_f093` (giọng bà ấy dùng ở 41/42 chương) sang `ngoc_linh_f087`, vì trong project đúc lại
`CHELY` (9 lần nhắc) giữ pin của giọng ấy còn NATASHA (19 lần nhắc, 42 chương) **không có pin**.
Một lượt đúc lại làm hỏng thứ nó được gọi ra để sửa là thứ phải đo, không phải thứ để đoán.

## Kết quả ranh giới 4 (đo 09:00 ngày 2026-09-16)

    tot hon 9 | xau hon 2 | khong ro 0

    TOT HON   ATHY (017, 020, 047), HERODOTUS (047, 048), MEKANZI (047), OTHELLO (047),
              IVEN (062), CAMIL (090)
    XAU HON   WOLF (047)     thai_son_f093   -> thanh_binh_f097   (da so 2 chuong)
              NATASHA (090)  ngoc_linh_f093  -> ngoc_linh_f087    (da so 41 chuong!)

Nên vòng đúc lại **lãi**, nhưng nó có một chế độ hỏng thật: một người **không có pin** với rất
nhiều chương có thể bị đẩy khỏi giọng đa số của mình. Xem docs/OPTIMISATION_QUEUE.md, mục "pin của
một giọng dùng chung được quyết bởi LÔ CUỐI, không bởi cuốn sách".

(Dòng trên từng mất một đường dẫn: tôi viết nó qua `python -c "..."` của bash, và dấu nháy ngược
quanh tên file trong một chuỗi nháy kép của bash là **thay thế lệnh** - bash chạy nó rồi nhét kết
quả rỗng vào. Cùng một cái bẫy đã bắt được trong `launch_batch.sh` sáng nay. Nội dung có nháy
ngược thì viết bằng công cụ ghi file, không qua `-c`.)
"""
from __future__ import annotations

import glob
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

VERSIONS = Path("D:/Novels/Audiobooks/book2/_versions")


def say(line: str = "") -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def _folded(name: object) -> str:
    return " ".join(str(name or "").strip().upper().split())


def voices_by_project() -> tuple[dict[tuple[str, str], list[tuple[float, str, str]]], dict]:
    """{(chuong, NGUOI): [(created_at, project, giong), ...]} + {(NGUOI, chuong): giong} cho ca sach."""
    per: dict[tuple[str, str], list[tuple[float, str, str]]] = defaultdict(list)
    for database in sorted(glob.glob(str(VERSIONS / "*" / "*" / "project.sqlite3"))):
        path = Path(database)
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            created = float(connection.execute("SELECT created_at FROM book").fetchone()[0] or 0)
            rows = connection.execute(
                "SELECT ch.title t, s.speaker, vp.voice_key, COUNT(*) n "
                "FROM segments s JOIN chapters ch ON ch.id = s.chapter_id "
                "JOIN voice_profiles vp ON vp.id = s.voice_profile_id "
                "WHERE ch.status = 'completed' GROUP BY ch.title, s.speaker, vp.voice_key"
            ).fetchall()
        except sqlite3.Error:
            connection.close()
            continue
        connection.close()
        # Một người có thể có nhiều giọng trong một chương (lỗi khác); lấy giọng nhiều câu nhất.
        best: dict[tuple[str, str], tuple[int, str]] = {}
        for row in rows:
            key = (str(row["t"]), _folded(row["speaker"]))
            if key[1] in {"NARRATOR", "UNKNOWN"} or key[1].startswith("NPC_LOCAL"):
                continue
            if key not in best or int(row["n"]) > best[key][0]:
                best[key] = (int(row["n"]), str(row["voice_key"]))
        for key, (_n, voice) in best.items():
            per[key].append((created, path.parent.name, voice))
    return per, {}


def main() -> int:
    wanted = [a for a in sys.argv[1:]] or ["017", "020", "047", "048", "062", "082", "090"]
    per, _ = voices_by_project()

    # Giọng đa số của mỗi người trên cả sách, tính theo SỐ CHƯƠNG, lấy bản MỚI NHẤT của mỗi chương.
    latest: dict[tuple[str, str], str] = {}
    for (title, name), takes in per.items():
        latest[(title, name)] = sorted(takes)[-1][2]
    majority_votes: dict[str, Counter[str]] = defaultdict(Counter)
    for (title, name), voice in latest.items():
        majority_votes[name][voice] += 1

    say(f"{len(per)} cap (chuong, nguoi) tren {len(majority_votes)} nguoi\n")
    better = worse = same = 0
    for title in wanted:
        lines = []
        for (t, name), takes in per.items():
            if t != title or len(takes) < 2:
                continue
            takes = sorted(takes)
            old_voice, new_voice = takes[-2][2], takes[-1][2]
            if old_voice == new_voice:
                continue
            # Đa số của người ấy TRỪ chương này ra, để phép so không tự chứng minh.
            votes = Counter(majority_votes[name])
            votes[new_voice] -= 1
            votes = Counter({v: c for v, c in votes.items() if c > 0})
            top = votes.most_common(1)[0][0] if votes else None
            verdict = (
                "TOT HON" if new_voice == top and old_voice != top
                else "XAU HON" if old_voice == top and new_voice != top
                else "khong ro"
            )
            if verdict == "TOT HON":
                better += 1
            elif verdict == "XAU HON":
                worse += 1
            else:
                same += 1
            lines.append(
                f"    {name:<16} {old_voice.replace('preset_', ''):<28} -> "
                f"{new_voice.replace('preset_', ''):<28} {verdict}"
                f"   (da so: {str(top).replace('preset_', '')}, {votes.get(top, 0)} chuong)"
            )
        say(f"=== chuong {title}: {len(lines)} nguoi doi giong" + (":" if lines else ""))
        for line in lines:
            say(line)
    say("")
    say(f"tot hon {better} | xau hon {worse} | khong ro {same}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
