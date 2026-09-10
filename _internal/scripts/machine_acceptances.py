"""Liệt kê mọi đoạn máy đã tự cho qua, kèm mốc thời gian trong file MP3.

    python scripts/machine_acceptances.py <project_dir>
    python scripts/machine_acceptances.py <project_dir> --markdown > bao_cao.md

Ràng buộc thứ ba của thiết kế (docs/SHIPPING_WITHOUT_A_LISTENER.md) là **không im lặng**.
Chủ sách ra lệnh không phải nghe, chứ không ra lệnh không được biết - hai chuyện khác nhau,
và cái thứ hai là chỗ cơ chế này có thể trở thành nói dối nếu không có gì như file này.

Cột đáng giá nhất là `mốc`: giây thứ mấy trong MP3 của chương. Với nó, muốn kiểm một đoạn
thì tua thẳng tới đó mất năm giây; không có nó thì phải nghe cả chương, tức là không ai kiểm.

File này báo cáo **hai** loại quyết định của máy, ở hai mục riêng:

- *cho qua* (`machine_audio_acceptances`) — audio giữ nguyên, chỉ cái chốt chương được mở;
- *thay* (`machine_take_substitutions`) — audio trong sách **không còn** là bản đường ống chọn
  lúc đầu, vì bản ấy bị cắt giữa câu và có một ứng viên đã nói xong.

Không trộn hai loại: khác biệt giữa "máy để nguyên và ghi sổ" với "máy đổi audio" là chính cái
người đọc báo cáo cần thấy.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def _timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def _offset(conn: sqlite3.Connection, segment_stable_id: str) -> tuple[str, float] | None:
    """Đoạn này nằm ở giây thứ mấy của chương nó thuộc về?

    Cộng dồn thời lượng mọi đoạn đứng trước nó trong cùng chương, cộng cả khoảng lặng giữa
    các đoạn - `break_ms` - vì bản ghép có chúng và tua theo con số thiếu khoảng lặng thì
    lệch dần, càng về cuối chương càng lệch.
    """
    row = conn.execute(
        "SELECT chapter_id, seq FROM segments WHERE stable_id=?", (segment_stable_id,)
    ).fetchone()
    if row is None:
        return None
    chapter = conn.execute(
        "SELECT chapter_index, title FROM chapters WHERE id=?", (row["chapter_id"],)
    ).fetchone()
    before = conn.execute(
        "SELECT COALESCE(SUM(wav_duration),0) d, COALESCE(SUM(break_ms),0) b "
        "FROM segments WHERE chapter_id=? AND seq<?",
        (row["chapter_id"], row["seq"]),
    ).fetchone()
    # Tiêu đề chương thường chính là số file nguồn ("019"), còn `chapter_index` là thứ tự
    # trong lô. In cả hai mà không lặp: "019 (thứ 1 trong lô)", chứ không phải "001 019".
    if chapter is None:
        return "?", 0.0
    title = str(chapter["title"]).strip()
    index = int(chapter["chapter_index"])
    label = f"{title} (thứ {index} trong lô)" if title else f"{index:03d}"
    return label, float(before["d"] or 0.0) + float(before["b"] or 0) / 1000.0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)

    database = args.project / "project.sqlite3"
    if not database.is_file():
        print(f"Không thấy {database}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "machine_audio_acceptances" not in names and "machine_take_substitutions" not in names:
        print("Project này có trước cơ chế tự cho qua - không có gì để báo cáo.")
        return 0

    rows = (
        list(
            conn.execute(
                "SELECT * FROM machine_audio_acceptances "
                "ORDER BY segment_stable_id, warning_code"
            )
        )
        if "machine_audio_acceptances" in names
        else []
    )
    # Việc **thay** một bản thu là loại quyết định khác với việc **cho qua** một bản thu, nên nó
    # có mục riêng chứ không trộn vào danh sách trên. Cho qua nghĩa là "audio giữ nguyên, chỉ
    # cái chốt chương được mở"; thay nghĩa là "audio trong sách không còn là bản đường ống chọn
    # lúc đầu". Gộp hai loại vào một danh sách là làm mất đúng cái khác biệt ấy.
    substitutions = (
        list(
            conn.execute(
                "SELECT * FROM machine_take_substitutions ORDER BY segment_stable_id"
            )
        )
        if "machine_take_substitutions" in names
        else []
    )
    heard_by_a_person = {
        (str(r[0]), str(r[1]))
        for r in conn.execute(
            "SELECT segment_stable_id, wav_sha256 FROM listener_audio_acceptances"
        )
    }

    def _report_substitutions() -> None:
        if not substitutions:
            return
        print()
        print("# Những bản thu máy đã thay" if args.markdown else "=== Bản thu máy đã thay")
        print()
        print(
            f"{len(substitutions)} lần máy bỏ một bản thu **bị cắt giữa câu** và dùng một ứng "
            "viên đã nói xong. Đương nhiệm chạm trần khung, tức bộ sinh tự khai nó chưa dứt "
            "câu; ứng viên tự kết thúc; và văn bản quá ngắn để ASR xếp hạng được hai bản."
        )
        for row in substitutions:
            placement = _offset(conn, str(row["segment_stable_id"]))
            at = _timestamp(placement[1]) if placement else "?"
            where = placement[0] if placement else "?"
            if args.markdown:
                print(f"- **Chương {where} {at}** `{row['segment_stable_id']}`")
                print(f"  - {row['reason']}")
            else:
                print(f"  ch{where} {at}  {row['segment_stable_id']}")
                print(f"        {row['reason']}")

    if not rows:
        if substitutions:
            print("Máy chưa tự cho qua đoạn nào.")
            _report_substitutions()
            return 0
        print("Máy chưa tự cho qua đoạn nào. Mọi thứ trong sách đều qua được phép kiểm.")
        return 0

    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        placement = _offset(conn, str(row["segment_stable_id"]))
        chapter = placement[0] if placement else "?"
        grouped.setdefault(chapter, []).append((row, placement))

    if args.markdown:
        print("# Những đoạn chưa ai nghe\n")
        print(
            f"{len(rows)} lần máy tự cho qua, trên {len(grouped)} chương. Mỗi dòng là một bản "
            "thu **không phép kiểm nào tán thành và không ai xác nhận** - nó vào sách vì "
            "vòng sửa đã cạn và ASR là thứ duy nhất phàn nàn.\n"
        )
    for chapter in sorted(grouped):
        print(f"\n## Chương {chapter}" if args.markdown else f"\n=== Chương {chapter}")
        for row, placement in grouped[chapter]:
            at = _timestamp(placement[1]) if placement else "?"
            already = (str(row["segment_stable_id"]), str(row["wav_sha256"])) in heard_by_a_person
            seen = " (sau đó đã có người nghe)" if already else ""
            if args.markdown:
                print(f"- **{at}** `{row['warning_code']}`{seen}")
                print(f"  - {row['reason']}")
            else:
                print(f"  {at}  {row['warning_code']}{seen}")
                print(f"        {row['reason']}")
    print(f"\nTổng: {len(rows)} đoạn.")
    _report_substitutions()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
