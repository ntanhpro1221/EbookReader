"""Gom MP3 của mọi lô thành một cuốn sách nói, theo **số chương thật** chứ không theo tên file.

    python scripts/assemble_book.py                          # chỉ liệt kê, không chép
    python scripts/assemble_book.py --apply --out <thư mục>  # chép thật

Viết trước khi cần, vì cái bẫy ở đây im lặng. Tên file MP3 có dạng `00004_003.mp3`: **tiền tố
là số thứ tự trong project, hậu tố mới là số chương**. Chương 003 nằm ở `00004_003.mp3` trong
lô 1 và ở `00001_003.mp3` trong lô vá — cùng một chương, hai tiền tố khác nhau, vì tiền tố đếm
theo dải chương mà project ấy bao. Gom 16 lô bằng cách sắp theo tên file là xáo trộn cả cuốn
sách, và xáo trộn theo kiểu không ai nhận ra cho tới khi ngồi nghe.

Nguồn sự thật là cột `chapters.title` trong SQLite, không phải tên file.

**Khi một chương có ở nhiều lô** — lô gốc hỏng rồi lô vá chạy lại — bản thắng là bản
`completed_at` **muộn nhất** trong số những bản `completed`. Không chọn theo tên tag: tag là
chuỗi người đặt, và một quy tắc sắp xếp dựa trên cách đặt tên sẽ hỏng đúng lúc ai đó đặt tên
khác đi. Script in ra mọi lần tranh chấp kèm bản thua, để việc chọn không im lặng.

Chỉ đọc SQLite; chỉ ghi khi có `--apply`, và chỉ ghi vào thư mục đích.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.io_utils import ffmpeg_executable, run_hidden  # noqa: E402

VERSIONS = Path(r"D:\Novels\Audiobooks\_versions")
SOURCE = Path(r"D:\Novels\Tools\Text")

# Tên "đĩa" của cả cuốn sách. Mặc định là một chỗ giữ chỗ: tên thật của truyện KHÔNG có ở đâu
# trong dữ liệu - `book.title` của mỗi project là slug của lô (`lo01b`, `lo05`), và dòng đầu của
# file nguồn là lời tán chuyện của người đăng. Đặt bằng `--album "Tên truyện"` khi biết.
DEFAULT_ALBUM = "Sách nói"


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def _candidates() -> dict[str, list[dict]]:
    """Mọi chương đã xuất bản được, gom theo số chương.

    Chỉ nhận chương `completed` **và** có file MP3 thật trên đĩa. Một dòng `completed` mà file
    đã bị xoá là chuyện có thật khi người ta dọn thư mục, và một cuốn sách thiếu chương thì
    đáng nổ ở đây chứ không đáng nổ trong tai người nghe.
    """
    found: dict[str, list[dict]] = {}
    if not VERSIONS.is_dir():
        return found
    for database in sorted(VERSIONS.glob("*/*/project.sqlite3")):
        try:
            conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT title, status, output_mp3, completed_at FROM chapters "
                    "WHERE status='completed' AND output_mp3 IS NOT NULL AND output_mp3 <> ''"
                ).fetchall()
            finally:
                conn.close()
        except sqlite3.Error:
            # Một project hỏng không nói gì về những project khác; bỏ qua và đi tiếp.
            continue
        for row in rows:
            mp3 = Path(str(row["output_mp3"]))
            if not mp3.is_absolute():
                mp3 = database.parent / mp3
            if not mp3.is_file() or mp3.stat().st_size <= 0:
                continue
            found.setdefault(str(row["title"]), []).append(
                {
                    "title": str(row["title"]),
                    "mp3": mp3,
                    "completed_at": float(row["completed_at"] or 0.0),
                    "version": database.parent.parent.name,
                    "project": database.parent.name,
                    "bytes": mp3.stat().st_size,
                }
            )
    return found


def _attempts() -> dict[str, float]:
    """Lần **thử** gần nhất cho mỗi chương, kể cả lần thất bại.

    Đây là thứ biến luật "bản mới nhất thắng" từ đúng-nhưng-im-lặng thành đúng-và-nói-ra. Nếu
    một lô mới hơn đã chạy chương này mà không cho ra MP3, thì bản thắng là một bản **lùi về
    quá khứ** — và một chương lấy từ chín phiên bản trước mang dàn giọng khác, cách đọc tên
    khác. Người nghe không thấy lỗi nào; họ chỉ thấy nhân vật đổi giọng ở đúng một chương.

    Đo lúc viết: chương 016 rơi về `v0.2.0-alpha.56` vì lô 1 hỏng nó và lô vá chưa xong.
    """
    latest: dict[str, float] = {}
    if not VERSIONS.is_dir():
        return latest
    for database in sorted(VERSIONS.glob("*/*/project.sqlite3")):
        try:
            conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(
                    "SELECT title, started_at, completed_at FROM chapters"
                ).fetchall()
            finally:
                conn.close()
        except sqlite3.Error:
            continue
        for row in rows:
            when = max(float(row["started_at"] or 0.0), float(row["completed_at"] or 0.0))
            title = str(row["title"])
            if when > latest.get(title, 0.0):
                latest[title] = when
    return latest


def wanted_tags(title: str, album: str, chapters_expected: int) -> dict[str, str]:
    """Thẻ mà một chương của CUỐN SÁCH phải có.

    Đo 01:30 ngày 2026-09-12 trên sách 118 chương: `album` là **38 giá trị khác nhau**, mỗi giá
    trị là slug của một project (`lo01b`, `lo03r_060`), và `track` là số thứ tự **trong project**
    nên 36 file cùng mang `track=1`. Máy nghe nhạc nào sắp theo thẻ - tức gần hết, khi cả thư
    mục được coi là một album - sẽ thấy 38 "đĩa" và trộn thứ tự chương. Sách chỉ nghe đúng thứ
    tự nếu người nghe sắp theo TÊN FILE.

    Không phải lỗi của đường ống: `assemble_chapter_atomic_with_metrics` ghi `album=book_title`
    và `track=chapter_index`, cả hai đúng ở tầng **một lô**. Cuốn sách mới là chỗ biết mình là
    một cuốn, nên nó là chỗ sửa.

    `track` = số chương thật kèm tổng số chương của nguồn (chương 000 thành track 0 - trung thực
    hơn là cộng một, và vẫn sắp đúng thứ tự).
    """
    numbered = f"{int(title)}/{chapters_expected}" if chapters_expected else str(int(title))
    return {"album": str(album), "title": str(title), "track": numbered}


def retag(path: Path, tags: dict[str, str]) -> bool:
    """Ghi lại thẻ, giữ nguyên audio (`-c copy`). True nếu đã ghi.

    Không sinh lại audio nên không đổi một mẫu nào; chỉ header ID3 đổi - tức kích thước file
    đích đổi vài trăm byte, và đó là lý do luật "chép khi khác kích thước" phải đi (xem
    `copy_needed`).
    """
    ffmpeg = ffmpeg_executable()
    temporary = path.with_suffix(".retag.mp3")
    command = [ffmpeg, "-v", "error", "-y", "-i", str(path), "-map", "0", "-c", "copy"]
    for key, value in sorted(tags.items()):
        command += ["-metadata", f"{key}={value}"]
    command.append(str(temporary))
    try:
        run_hidden(command, timeout=300.0)
        temporary.replace(path)
        return True
    except (OSError, subprocess.SubprocessError):
        temporary.unlink(missing_ok=True)
        return False


def previous_manifest(out: Path) -> dict[str, dict]:
    """{chương: hàng manifest} của lần ghép trước; rỗng nếu chưa có."""
    try:
        payload = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entries = payload if isinstance(payload, list) else payload.get("chapters", [])
    return {str(item.get("title")): item for item in entries if item.get("title")}


def copy_needed(destination: Path, item: dict, before: dict | None) -> bool:
    """Có phải chép lại chương này không - hỏi theo GỐC GÁC, không theo kích thước file đích.

    Luật cũ so `destination.stat().st_size` với `item["bytes"]`. Nó đúng cho tới khi có bước ghi
    lại thẻ: ghi thẻ đổi kích thước file đích, nên lần ghép sau thấy "khác kích thước" và chép
    lại cả 119 file (~2 GB) mỗi lần, rồi ghi thẻ, rồi lại khác. Câu hỏi thật không phải "file
    đích có bằng nguồn không" mà **"file đích có phải đúng bản này không"**, và manifest đã ghi
    đủ để trả lời: version, project, bytes.
    """
    if not destination.is_file() or destination.stat().st_size <= 0:
        return True
    if not before:
        return True
    return (
        str(before.get("version") or "") != str(item["version"])
        or str(before.get("project") or "") != str(item["project"])
        or int(before.get("bytes") or -1) != int(item["bytes"])
    )


def retag_needed(copied_now: bool, want: dict[str, str], before: dict | None) -> bool:
    """Có phải ghi lại thẻ không, hỏi bằng MANIFEST chứ không đọc file.

    Đọc thẻ thật thì cần `ffprobe`, mà bản ffmpeg dự án dùng (`imageio_ffmpeg`) chỉ có `ffmpeg`.
    Manifest là sổ của chính bước này: nó ghi thẻ đã viết, nên so với thẻ muốn viết là đủ. Một
    bản vừa được chép về thì đang mang thẻ của LÔ, nên luôn phải ghi lại.

    Giới hạn, nói ra: ai sửa thẻ bằng công cụ khác thì bước này không biết. Manifest của lần
    ghép đầu tiên chưa có mục `tags`, nên lần chạy đầu sau bản vá sẽ ghi lại thẻ cho mọi chương
    - đúng điều cần, vì cả 118 chương đang mang album là slug của lô.
    """
    if copied_now:
        return True
    return dict((before or {}).get("tags") or {}) != dict(want)


def _expected() -> list[str]:
    if not SOURCE.is_dir():
        return []
    return sorted(path.stem for path in SOURCE.glob("*.txt"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path(r"D:\Novels\Audiobooks\_book"))
    parser.add_argument("--apply", action="store_true", help="Chép thật thay vì chỉ liệt kê")
    parser.add_argument(
        "--album",
        default=DEFAULT_ALBUM,
        help=f"Tên đĩa ghi vào mọi chương (mặc định {DEFAULT_ALBUM!r}; tên thật của truyện"
        " không có ở đâu trong dữ liệu)",
    )
    args = parser.parse_args(argv)

    found = _candidates()
    expected = _expected()
    if not found:
        _say("Không tìm thấy chương nào đã xuất bản.")
        return 2

    winners: dict[str, dict] = {}
    contested = 0
    for title, options in sorted(found.items()):
        options.sort(key=lambda item: item["completed_at"], reverse=True)
        winners[title] = options[0]
        if len(options) > 1:
            contested += 1
            _say(f"chương {title}: {len(options)} bản, lấy {options[0]['version']}")
            for loser in options[1:]:
                _say(f"    bỏ  {loser['version']}/{loser['project']}  {loser['mp3'].name}")

    _say("")
    _say(f"{len(winners)} chương có MP3; {contested} chương có nhiều hơn một bản.")
    if expected:
        missing = [title for title in expected if title not in winners]
        extra = [title for title in winners if title not in expected]
        _say(f"nguồn có {len(expected)} chương; **thiếu {len(missing)}**.")
        if missing:
            head = ", ".join(missing[:20])
            tail = "" if len(missing) <= 20 else f" … và {len(missing) - 20} chương nữa"
            _say(f"  thiếu: {head}{tail}")
        if extra:
            _say(f"  có MP3 nhưng nguồn không có: {', '.join(extra[:10])}")
    total = sum(item["bytes"] for item in winners.values())
    _say(f"tổng {total / 2**30:.2f} GB")

    # Chương nào phải lùi về một lô cũ hơn lần thử gần nhất.
    attempts = _attempts()
    stale = [
        (title, item)
        for title, item in sorted(winners.items())
        if attempts.get(title, 0.0) > item["completed_at"] + 1.0
    ]
    if stale:
        _say("")
        _say(f"CẢNH BÁO: {len(stale)} chương phải lùi về một lô CŨ HƠN lần chạy gần nhất.")
        _say("  Một lô mới hơn đã chạy chúng và không cho ra MP3, nên bản đang dùng mang dàn")
        _say("  giọng và cách đọc của phiên bản cũ. Không cổng nào bắt được: mỗi chương tự nó")
        _say("  vẫn hợp lệ, chỉ có cuốn sách là không nhất quán.")
        for title, item in stale:
            _say(f"  chương {title}: đang lấy {item['version']}")

    if not args.apply:
        _say("")
        _say("Lượt thử, chưa chép gì. Thêm --apply để chép.")
        return 0

    # Tên đích đánh số theo **số chương thật**, nên trình phát sắp đúng thứ tự dù script này
    # có chạy lại theo thứ tự nào.
    args.out.mkdir(parents=True, exist_ok=True)
    width = max((len(title) for title in winners), default=3)
    before = previous_manifest(args.out)
    written_tags: dict[str, dict[str, str]] = {}
    copied = tagged = 0
    for title, item in sorted(winners.items()):
        destination = args.out / f"{title.zfill(width)}.mp3"
        copied_now = copy_needed(destination, item, before.get(title))
        if copied_now:
            temporary = destination.with_suffix(".part")
            shutil.copyfile(item["mp3"], temporary)
            temporary.replace(destination)
            copied += 1
        # Thẻ của CUỐN SÁCH, không phải thẻ của lô. Xét từng chương chứ không chỉ chương vừa
        # chép: 118 chương đã lên sách trước bước này đều mang album là slug của lô nó ra đời.
        want = wanted_tags(title, str(args.album), len(expected))
        if retag_needed(copied_now, want, before.get(title)):
            if retag(destination, want):
                tagged += 1
                written_tags[title] = want
            else:
                _say(f"  KHÔNG ghi được thẻ cho {destination.name} - audio vẫn đúng, thẻ vẫn cũ")
        else:
            written_tags[title] = dict((before.get(title) or {}).get("tags") or want)
    # Gốc gác từng chương. Một cuốn 478 chương được ghép từ khoảng hai mươi project, và không
    # có file này thì sáu tháng nữa không ai trả lời được "chương 137 ra từ lượt chạy nào" —
    # câu hỏi đầu tiên người ta hỏi khi nghe thấy một chỗ lạ tai.
    #
    # Không tính sha256: 478 file nhân ~20 MB là mười gigabyte băm cho một câu hỏi về **nguồn
    # gốc**, không phải về toàn vẹn. Kích thước và tên project đủ để truy ngược.
    manifest = {
        "chapters": [
            {
                "title": title,
                "file": f"{title.zfill(width)}.mp3",
                "version": item["version"],
                "project": item["project"],
                "source_file": item["mp3"].name,
                "bytes": item["bytes"],
                # Thẻ bước này đã ghi, để lần sau biết có phải ghi lại không mà không cần đọc
                # file (bản ffmpeg của dự án không kèm `ffprobe`).
                "tags": written_tags.get(title, {}),
            }
            for title, item in sorted(winners.items())
        ],
        "chapters_expected": len(expected),
        "chapters_present": len(winners),
        "missing": [title for title in expected if title not in winners],
        "fell_back_to_an_older_batch": [title for title, _item in stale],
    }
    path = args.out / "manifest.json"
    temporary = path.with_suffix(".part")
    io_text = json.dumps(manifest, ensure_ascii=False, indent=1)
    temporary.write_text(io_text, encoding="utf-8")
    temporary.replace(path)

    _say("")
    _say(f"Đã chép {copied} chương mới vào {args.out} ({len(winners)} chương tổng).")
    if tagged:
        _say(f"Đã ghi lại thẻ cho {tagged} chương: album {args.album!r}, track = số chương thật.")
        if str(args.album) == DEFAULT_ALBUM:
            _say('  (tên đĩa đang là chỗ giữ chỗ; đặt tên thật bằng --album "Tên truyện")')
    _say(f"Gốc gác từng chương ghi ở {path.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
