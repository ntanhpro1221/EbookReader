"""`amoniac`, `urê`: danh từ vay mượn viết bằng chữ Việt — lớp này có thật tốn gì không?

    python scripts/measure_a_loanword_noun.py            # cả hai nửa
    python scripts/measure_a_loanword_noun.py --source    # chỉ đếm trên nguồn
    python scripts/measure_a_loanword_noun.py --outcome   # chỉ đếm kết cục từng đoạn

Chỉ đọc: quét nguồn `.txt` của cuốn đang cấu hình và các `project.sqlite3` của nó.

## Ca thật (lô 4 cuốn 2, đêm 15→16/09)

    chuong 157  "À… khí amoniac."  -> Whisper "À, khí âm mồ này ố."  0,56  THAT BAI
    chuong 158  "Là urê."          -> Whisper "Là một rời!"          0,12  ship kem canh bao

Cả hai là **danh từ vay mượn**, không phải tên người, nên `analysis.py` không sinh cách đọc cho chúng
(luật bỏ ứng viên xuất hiện một lần, không phải người nói, không viết hoa giữa câu — luật ấy có chủ ý
và chính nó chặn phantom). Giọng đọc tự xử, và ASR không bắc được cầu qua đó.

## Hai nửa, và vì sao phải có nửa thứ hai

**Nửa một, trên nguồn:** 1.796 lần xuất hiện, 567 cặp (từ, chương), **533 cặp ở chương chưa sản
xuất** — `nguyên tử` 801 lần / 232 chương, `electron` 560 / 112, `urê` 80 / 24. Một con số trông đáng
báo động, và nó **gộp hai thứ khác hẳn nhau**: Hán-Việt bình thường (`nguyên tử`, `lưu huỳnh`, `dung
dịch`) mà giọng đọc không hề vấp, với vay mượn La-tinh (`amoniac`, `urê`, `electron`) mới là lớp đã
thất bại thật.

**Nửa hai, trên 15.024 đoạn ĐÃ THU** — và đây là nửa đổi nỗi lo thành con số (04:20 ngày 16-09):

    nhom                 tong   sach  canh bao  hong   ti le xau
    vay muon La-tinh       31     21         9     1      32,3%
    Han-Viet thuong        58     49         9     0      15,5%
    khong co tu nao     14935  11333      3570    32      24,1%   <- NEN

**Tỉ lệ nền là 24,1%.** Nhóm vay mượn 32,3% trên n=31 nghĩa là 10 đoạn "xấu" ở nơi nền dự đoán 7,5 —
chênh hai đoạn rưỡi, tức không nói gì cả. Và gần như mọi cảnh báo ở **cả ba nhóm** là
`ASR_LOCKED_NAME_ANCHOR_MISMATCH`, lớp đã đo riêng là bắn trên 21–27% mọi đoạn và tốn ~0 GPU. Chính
đoạn `urê` bị cảnh báo có **độ giống 0,99**: cảnh báo ấy nói về `Lucien`, không nói về `urê`.

Còn lại đúng **1 đoạn thất bại trên 15.024** vì lớp này. Suy ra cho 533 cặp còn lại: một nhúm đoạn
máy-nhận rải trên 776 chương. **Không viết mã** — và nếu có ai muốn xử ca 157 thì thêm một dòng vào
sổ cách đọc của lô ấy là xong, đúng như ca `Gossett` chương 296.

Bài học đáng giữ hơn cả kết luận: nửa một đếm **số lần xuất hiện trong nguồn**, thứ không phải một cái
giá. Chỉ khi đếm **kết cục từng đoạn** và so với **nền** thì 1.796 mới teo lại thành 1.
"""
from __future__ import annotations

import argparse
import glob
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from scripts.book_paths import SOURCE_DIR, VERSIONS, describe  # noqa: E402
except ImportError:  # chạy trực tiếp
    from book_paths import SOURCE_DIR, VERSIONS, describe  # noqa: E402

# Chính tả không theo vần Việt: đây là lớp giọng đọc phải tự xử.
LATIN = [
    "amoniac", "urê", "ure", "electron", "proton", "nơtron", "notron", "ion", "carbon",
    "cacbon", "metan", "etan", "benzen", "hydro", "hiđro", "oxy", "oxi", "nitơ", "nito",
    "kali", "natri", "canxi", "magie", "clo", "brom", "iot", "protein", "enzym", "vitamin",
    "polime", "glucozơ", "xenlulozơ", "ancol", "andehit", "sunfat", "sulfat", "nitrat",
    "photpho", "phốt pho", "bazơ",
]
# Hán-Việt bình thường: có trong bảng để thấy nó KHÔNG phải cùng một lớp.
SINO = [
    "nguyên tử", "phân tử", "hợp chất", "dung dịch", "lưu huỳnh", "xúc tác", "kết tủa", "axit",
]


def _say(line: str) -> None:
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def _patterns(words: list[str]) -> dict[str, re.Pattern[str]]:
    return {w: re.compile(rf"(?<!\w){re.escape(w)}(?!\w)", re.IGNORECASE) for w in words}


def pinned_surfaces(versions: Path) -> set[str]:
    out: set[str] = set()
    for database in sorted(glob.glob(str(versions / "*" / "*" / "project.sqlite3"))):
        connection = sqlite3.connect(f"file:{Path(database).as_posix()}?mode=ro", uri=True)
        try:
            for row in connection.execute(
                "SELECT surface FROM pronunciations WHERE spoken_form IS NOT NULL"
            ):
                out.add(str(row[0]).casefold())
        except sqlite3.Error:
            pass
        finally:
            connection.close()
    return out


def on_the_source(source: Path, versions: Path, produced: int) -> None:
    pinned = pinned_surfaces(versions)
    patterns = _patterns(LATIN + SINO)
    counts: Counter[str] = Counter()
    chapters_of: dict[str, set[str]] = defaultdict(set)
    files = sorted(source.glob("*.txt"))
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        folded = text.casefold()
        for word, pattern in patterns.items():
            if word not in folded:
                continue
            found = len(pattern.findall(text))
            if found:
                counts[word] += found
                chapters_of[word].add(path.stem)

    _say(f"{len(files)} chương nguồn; {len(counts)} từ có mặt")
    _say("")
    _say(f"{'tu':<14}{'lop':<12}{'so lan':>7}{'chuong':>8}{'cach doc':>10}  chuong dau")
    ahead = 0
    for word, count in counts.most_common():
        chapters = sorted(chapters_of[word])
        ahead += sum(1 for c in chapters if not c.isdigit() or int(c) > produced)
        _say(
            f"{word:<14}{'La-tinh' if word in LATIN else 'Han-Viet':<12}{count:>7}"
            f"{len(chapters):>8}{'co' if word in pinned else 'KHONG':>10}"
            f"  {', '.join(chapters[:5])}"
        )
    _say("")
    _say(
        f"Tổng {sum(counts.values())} lần xuất hiện, "
        f"{sum(len(v) for v in chapters_of.values())} cặp (từ, chương); "
        f"{ahead} cặp ở chương > {produced} (chưa sản xuất)."
    )
    _say("Số này KHÔNG phải một cái giá - xem nửa dưới.")


def on_the_takes(versions: Path) -> None:
    latin, sino = _patterns(LATIN), _patterns(SINO)
    seen: set[tuple[str, str]] = set()
    tally: dict[str, Counter[str]] = {
        "vay muon La-tinh": Counter(),
        "Han-Viet thuong": Counter(),
        "khong co tu nao": Counter(),
    }
    failures: list[str] = []
    for database in sorted(glob.glob(str(versions / "*" / "*" / "project.sqlite3"))):
        connection = sqlite3.connect(f"file:{Path(database).as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT s.stable_id, s.status, s.warning_code, s.text, s.asr_similarity sim, "
                "ch.title t FROM segments s JOIN chapters ch ON ch.id = s.chapter_id "
                "WHERE (s.wav_sha256 IS NOT NULL AND s.wav_sha256 != '') OR s.status = 'failed'"
            ).fetchall()
        except sqlite3.Error:
            connection.close()
            continue
        for row in rows:
            key = (str(row["t"]), str(row["stable_id"]))
            if key in seen:
                continue
            seen.add(key)
            text = str(row["text"] or "")
            group = (
                "vay muon La-tinh" if any(p.search(text) for p in latin.values())
                else "Han-Viet thuong" if any(p.search(text) for p in sino.values())
                else "khong co tu nao"
            )
            code = str(row["warning_code"] or "")
            outcome = "hong" if str(row["status"]) == "failed" else "canh bao" if code else "sach"
            tally[group][outcome] += 1
            tally[group]["tong"] += 1
            if outcome == "hong" and group != "khong co tu nao":
                similarity = row["sim"]
                failures.append(
                    f"ch {row['t']} [{group}] {code} "
                    f"(giống {round(float(similarity), 2) if similarity is not None else '-'}): "
                    f"{text[:60]}"
                )
        connection.close()

    _say(f"{len(seen)} đoạn đã thu (gộp trùng theo chương + stable_id)")
    _say("")
    _say(f"{'nhom':<20}{'tong':>7}{'sach':>7}{'canh bao':>10}{'hong':>6}{'ti le xau':>11}")
    for group, counter in tally.items():
        total = counter["tong"] or 1
        bad = counter["canh bao"] + counter["hong"]
        mark = "   <- NEN" if group == "khong co tu nao" else ""
        _say(
            f"{group:<20}{counter['tong']:>7}{counter['sach']:>7}{counter['canh bao']:>10}"
            f"{counter['hong']:>6}{100 * bad / total:>10.1f}%{mark}"
        )
    _say("")
    if failures:
        _say("Đoạn THẤT BẠI có từ vay mượn:")
        for line in failures:
            _say(f"   {line}")
    else:
        _say("Không đoạn nào có từ vay mượn bị thất bại.")
    _say("")
    _say("So với NỀN, không với 0: gần như mọi cảnh báo ở cả ba nhóm là ASR_LOCKED_NAME_ANCHOR_MISMATCH.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", action="store_true", help="chỉ nửa đếm trên nguồn")
    parser.add_argument("--outcome", action="store_true", help="chỉ nửa đếm kết cục")
    parser.add_argument("--produced", type=int, default=139, help="chương cuối đã sản xuất")
    args = parser.parse_args(argv)

    _say(describe())
    _say("")
    if not args.outcome:
        on_the_source(SOURCE_DIR, VERSIONS, args.produced)
        _say("")
    if not args.source:
        on_the_takes(VERSIONS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
