"""So hai lượt chạy cùng dải chương: chương nào đổi kết cục, và vì sao.

    python scripts/compare_runs.py <project cũ> <project mới>

Viết cho lượt đo cơ chế tự cho qua (alpha.60 → alpha.62), nhưng không có gì riêng cho nó:
mọi so sánh đều theo **tiêu đề chương**, không theo `chapter_index`, vì hai lượt cùng dải vẫn
có thể đánh số trong lô khác nhau nếu dải lệch một file.

Cột `chưa ai nghe` là thứ đáng nhìn nhất khi so hai lượt quanh một thay đổi về cổng chặn: một
chương chuyển từ `failed` sang `completed` mà mang theo con số ấy thì nó xuất bản **nhờ máy tự
cho qua**, chứ không phải nhờ bản thu khá lên. Hai chuyện rất khác nhau và rất dễ lẫn.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def _open(project: Path) -> sqlite3.Connection:
    database = project / "project.sqlite3"
    if not database.is_file():
        raise SystemExit(f"Không thấy {database}")
    conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _chapters(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {str(row["title"]): row for row in conn.execute("SELECT * FROM chapters")}


def _machine_accepted(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "machine_audio_acceptances" not in names:
        return set()
    return {
        (str(a), str(b))
        for a, b in conn.execute(
            "SELECT segment_stable_id, wav_sha256 FROM machine_audio_acceptances"
        )
    }


def _unheard_per_chapter(conn: sqlite3.Connection) -> dict[str, int]:
    accepted = _machine_accepted(conn)
    if not accepted:
        return {}
    heard = {
        (str(a), str(b))
        for a, b in conn.execute(
            "SELECT segment_stable_id, wav_sha256 FROM listener_audio_acceptances"
        )
    }
    counts: dict[str, int] = {}
    for row in conn.execute(
        "SELECT ch.title t, s.stable_id, s.wav_sha256 FROM segments s "
        "JOIN chapters ch ON ch.id = s.chapter_id"
    ):
        key = (str(row["stable_id"]), str(row["wav_sha256"] or ""))
        if key in accepted and key not in heard:
            counts[str(row["t"])] = counts.get(str(row["t"]), 0) + 1
    return counts


def _voice_drift(before: sqlite3.Connection, after: sqlite3.Connection) -> tuple[int, int, list[str]]:
    """Bao nhiêu đoạn được đúc **giọng khác** giữa hai lượt?

    Biến gây nhiễu duy nhất còn lại của phép so sánh, và nó im lặng. Hạt giống sinh audio là
    `stable_int(f"segment::{stable_id}::{voice_key}::{seed_salt}")`, nên `stable_id` trùng
    khít vẫn chưa đủ: đổi giọng là đổi hạt giống là đổi bản thu, và lúc ấy "chương này khá lên"
    có thể chỉ là một lần bốc thăm khác.

    Trả về (số đoạn so được, số đoạn lệch giọng, vài ví dụ).
    """
    def voices(conn: sqlite3.Connection) -> dict[str, str]:
        return {
            str(row["stable_id"]): f"{row['speaker']}|{row['voice_profile_id']}"
            for row in conn.execute(
                "SELECT stable_id, speaker, voice_profile_id FROM segments"
            )
        }

    old_voices, new_voices = voices(before), voices(after)
    shared = set(old_voices) & set(new_voices)
    drifted = sorted(k for k in shared if old_voices[k] != new_voices[k])
    return len(shared), len(drifted), drifted[:5]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args(argv)

    before, after = _open(args.before), _open(args.after)
    old, new = _chapters(before), _chapters(after)
    unheard = _unheard_per_chapter(after)

    shared = sorted(set(old) & set(new))
    if not shared:
        print("Hai project không có chương nào trùng tiêu đề - có phải cùng dải không?")
        return 2

    # Nói ra trước khi in bất cứ con số nào. Chạy giữa chừng thì `voice_profile_id` còn rỗng,
    # và cột lệch giọng sẽ báo 1357/1357 - một cảnh báo đúng theo dữ liệu và sai hoàn toàn về ý
    # nghĩa. Tôi đã suýt đọc nhầm nó đúng một lần, nên nó phải tự nói.
    unfinished = [t for t in shared if str(new[t]["status"]) in {"pending", "analyzing", "verifying"}]
    if unfinished:
        print(
            f"LƯU Ý: {len(unfinished)}/{len(shared)} chương của project SAU chưa chạy xong "
            f"({', '.join(unfinished[:6])}...).\n"
            "  Mọi con số dưới đây là ảnh chụp giữa chừng: chương chưa chạy đọc thành 'hỏng\n"
            "  thêm', và đoạn chưa đúc giọng đọc thành 'đổi giọng'. Đợi lượt chạy xong.\n"
        )

    print(f"{'chương':10s} {'trước':11s} {'sau':11s} chưa ai nghe")
    fixed = broke = same = 0
    for title in shared:
        a, b = str(old[title]["status"]), str(new[title]["status"])
        n = unheard.get(title, 0)
        mark = "  " if a == b else ("→✓" if b == "completed" else "→✗")
        if a == b:
            same += 1
        elif b == "completed":
            fixed += 1
        else:
            broke += 1
        print(f"{title:10s} {a:11s} {b:11s} {n if n else '':>12} {mark}")

    print()
    print(f"gỡ được: {fixed}   hỏng thêm: {broke}   giữ nguyên: {same}")

    compared, drifted, examples = _voice_drift(before, after)
    print()
    if drifted:
        print(f"CẢNH BÁO: {drifted}/{compared} đoạn đổi giọng giữa hai lượt.")
        print("  Hạt giống sinh audio phụ thuộc giọng, nên những đoạn ấy có bản thu khác vì")
        print("  một lý do KHÔNG liên quan tới thay đổi đang đo.")
        print("  Ví dụ: " + ", ".join(examples))
    else:
        print(f"đúc giọng: {compared} đoạn, không đoạn nào đổi — phép so sánh sạch")
    total_unheard = sum(unheard.values())
    if total_unheard:
        print(
            f"\n{total_unheard} đoạn vào sách mà chưa ai nghe, trên "
            f"{len(unheard)} chương. Xem `scripts/machine_acceptances.py` để có mốc thời gian."
        )
    # Một chương gỡ được mà không mang đoạn nào chưa ai nghe thì nó xuất bản vì **bản thu khá
    # lên thật** - đó là thắng lợi của bản vá, không phải của cơ chế tự cho qua. Tách hai loại
    # ra ở đây, vì gộp lại là cách dễ nhất để tự khen nhầm.
    earned = [t for t in shared
              if str(old[t]["status"]) != "completed"
              and str(new[t]["status"]) == "completed"
              and not unheard.get(t)]
    if earned:
        print(f"\nGỡ được KHÔNG cần cho qua đoạn nào: {', '.join(earned)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
