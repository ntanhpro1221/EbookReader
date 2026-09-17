"""Sách đã ghép: có chương nào HỤT TIẾNG so với số chữ của chính nó không?

    runtime/.venv/Scripts/python.exe scripts/audit_the_shipped_book.py

Chỉ đọc. Mỗi chương trên sách được so **giây audio / ký tự nguồn** với trung vị của cả sách: một
chương mất cả cụm thì tỉ lệ ấy tụt hẳn.

**Chia việc với `assemble_book.py --verify`, đừng làm trùng:** `--verify` hỏi *"file trong sách có
đúng là file của project không"* (thời lượng ±0,05 s, kênh, sample rate, sha256 khi trùng thời
lượng). Nó im lặng đúng ở một chỗ: nếu **chính project** đã mất một đoạn thì hai file vẫn khớp nhau
hoàn hảo. Script này hỏi câu còn lại: *"chương này có đủ tiếng so với số chữ của nó không"* — phép so
duy nhất đi ra ngoài dây chuyền, vì nó dùng văn bản nguồn làm mốc. Dự án từng mất audio của một đoạn
đúng theo kiểu ấy (`c00007_s0000074`).

**Độ nhạy, nói cho đúng:** đo 18-09 trên 219 chương cuốn 2 thì dải thực tế là **94%..108%** của
trung vị — rất chặt — nên dải chấp nhận đặt ở `[90%, 112%]`. Một chương ~80 đoạn mất MỘT đoạn chỉ
hụt ~1%: phép này **không** thấy. Nó bắt mất cả cụm (một đoạn văn, một trang), tức đúng loại hỏng mà
người nghe nhận ra ngay mà máy lại im lặng.
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
from pathlib import Path

BOOK = Path(r"D:\Novels\Audiobooks\book2\_book")
SOURCE = Path(r"D:\Novels\Ebook Reader\Text_Tmp")


def duration_seconds(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
    try:
        return float(out)
    except ValueError:
        return float("nan")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    manifest = json.loads((BOOK / "manifest.json").read_text(encoding="utf-8"))
    chapters = manifest["chapters"]
    print(f"manifest: {len(chapters)} chuong | mong doi {manifest.get('chapters_expected')} | "
          f"co {manifest.get('chapters_present')} | thieu {len(manifest.get('missing') or [])} | "
          f"tut ve lo cu: {manifest.get('fell_back_to_an_older_batch')}")
    files = sorted(BOOK.glob("*.mp3"))
    listed = {entry["file"] for entry in chapters}
    on_disk = {path.name for path in files}
    if listed - on_disk:
        print(f"  CHAN: manifest ke {len(listed - on_disk)} file khong co tren dia: {sorted(listed - on_disk)[:5]}")
    if on_disk - listed:
        print(f"  la: {len(on_disk - listed)} file tren dia khong co trong manifest: {sorted(on_disk - listed)[:5]}")

    sources = {path.stem.split("_", 1)[-1]: path for path in SOURCE.glob("*.txt")}
    rows = []
    for entry in chapters:
        path = BOOK / entry["file"]
        if not path.exists():
            continue
        title = str(entry["title"])
        source = sources.get(title)
        characters = len(source.read_text(encoding="utf-8", errors="replace")) if source else 0
        seconds = duration_seconds(path)
        rows.append((title, seconds, characters, seconds / characters if characters else float("nan"),
                     str(entry.get("version", "")), int(entry.get("bytes", 0))))
    good = [row[3] for row in rows if row[3] == row[3] and row[2] > 0]
    median = statistics.median(good)
    total_hours = sum(row[1] for row in rows if row[1] == row[1]) / 3600.0
    shares = sorted(row[3] / median for row in rows if row[3] == row[3] and row[2] > 0)
    print(f"\n{len(rows)} chuong, tong {total_hours:.1f} gio | giay/ky tu trung vi {median:.4f} | "
          f"dai thuc te {shares[0]:.0%}..{shares[-1]:.0%} cua trung vi")
    print(f"{'chuong':7} {'giay':>8} {'ky tu':>7} {'giay/ky tu':>11} {'so trung vi':>12}  ban")
    flagged = 0
    for title, seconds, characters, ratio, version, _bytes in rows:
        if ratio != ratio or characters == 0:
            print(f"{title:7} {seconds:8.1f} {characters:7} {'?':>11} {'khong co nguon':>12}  {version}")
            flagged += 1
            continue
        share = ratio / median
        if share < 0.90 or share > 1.12:
            print(f"{title:7} {seconds:8.1f} {characters:7} {ratio:11.4f} {share:11.0%}  {version}")
            flagged += 1
    print(f"\n{flagged} chuong lech ngoai [90%, 112%] cua trung vi" if flagged
          else "\nkhong chuong nao lech ngoai [90%, 112%] cua trung vi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
