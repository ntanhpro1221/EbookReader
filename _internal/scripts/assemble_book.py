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
from ebook_reader.text_processing import sha256_file  # noqa: E402

try:
    from scripts.book_paths import ALBUM, BOOK, SOURCE_DIR as SOURCE, VERSIONS  # noqa: E402
except ImportError:  # chạy trực tiếp: python scripts/x.py
    from book_paths import ALBUM, BOOK, SOURCE_DIR as SOURCE, VERSIONS  # noqa: E402
# `SOURCE` từng ghim cứng `D:/Novels/Tools/Text` - thư mục nguồn CŨ của cuốn 1, bị xoá ngày
# 13-09 và khôi phục sang `Ebook Reader/Text`. Hệ quả im lặng: `_expected()` đọc một thư mục
# không tồn tại nên trả về rỗng, và phép kiểm "nguồn có N chương, **thiếu M**" chưa bao giờ
# chạy cho cuốn nào - kể cả cuốn 2, vốn chưa từng dùng đường dẫn ấy. Tìm ra 00:15 ngày
# 2026-09-16, cùng họ với `before_a_batch._versions` và bộ canh của `apply_all` đã sửa cùng
# ngày: mỗi lần `book_paths` dẹp một đường dẫn chép tay, phải đi tìm những chỗ còn lại.

# Tên "đĩa" của cả cuốn sách, và nó thuộc về CUỐN nên nó ở `book_paths` (đọc từ `EBOOK_ALBUM`),
# không phải một hằng số ở đây. Bước 7 của `boundary.sh` gọi script này **không** kèm
# `--album`, nên một hằng số ở đây là một cái tên bị mọi lần ghép sau ghi đè - đúng cái bẫy đã
# chờ sẵn lúc 01:40 ngày 2026-09-16, ngay sau khi hai cuốn vừa có tên thật.
#
# Tên ấy không có ở đâu trong dữ liệu (`book.title` của mỗi project là slug của lô, và dòng đầu
# file nguồn là lời tán chuyện của người đăng) — nó được **tra từ internet** bằng tên nhân vật
# trong truyện, không phải đoán từ ký ức. `--album` vẫn đè được khi cần một lần.
DEFAULT_ALBUM = ALBUM
# Chỗ giữ chỗ cũ, giữ lại chỉ để nhận ra một cuốn CHƯA có tên: `EBOOK_ALBUM` không đặt thì
# `book_paths` trả tên của cuốn đang sản xuất, nên một cuốn thứ ba sẽ mang tên cuốn 2 nếu ai đó
# quên `book<N>.env` - và lời nhắc dưới đây là chỗ duy nhất nói ra điều ấy.
PLACEHOLDER_ALBUM = "Sách nói"


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


def probe_audio(path: Path) -> tuple[float, int | None, int | None] | None:
    """(giây, số kênh, sample rate) của một file, hoặc None nếu không đo được.

    Dùng `ffprobe` của hệ thống: bản ffmpeg dự án nhúng (`imageio_ffmpeg`) chỉ có `ffmpeg`, nên
    hàm này có thể trả None trên một máy không cài ffmpeg đầy đủ - và `--verify` nói ra điều đó
    thay vì báo cuốn sách hỏng.
    """
    probe = shutil.which("ffprobe")
    if not probe or not path.is_file():
        return None
    try:
        done = run_hidden(
            [
                probe, "-v", "error", "-show_entries",
                "format=duration:stream=channels,sample_rate", "-of", "json", str(path),
            ],
            timeout=120.0,
        )
        payload = json.loads(done.stdout or "{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    duration = float((payload.get("format") or {}).get("duration") or 0.0)
    stream = (payload.get("streams") or [{}])[0]
    channels = int(stream["channels"]) if stream.get("channels") is not None else None
    sample_rate = int(stream["sample_rate"]) if stream.get("sample_rate") is not None else None
    return duration, channels, sample_rate


def verify(out: Path) -> tuple[int, list[str]]:
    """Cuốn sách có đúng là thứ manifest nói không. (số chương đã kiểm, danh sách lời phàn nàn).

    Manifest ghi **gốc gác** (version, project, source_file) nhưng chưa ai kiểm rằng file trong
    sách thật sự là chương ấy. Một lần chép sai, hay một project bị xoá sau khi ghép, đều im
    lặng: tên file vẫn đúng, thẻ vẫn đúng, và người nghe mới là người phát hiện.

    So thời lượng (±0,05 giây), số kênh và sample rate giữa file trong sách và file gốc trong
    project. Không so byte: ghi lại thẻ đổi header, và giải mã 118 chương để so PCM là hai giờ
    máy cho một câu hỏi mà thời lượng đã trả lời.

    Đo lần đầu 01:45 ngày 2026-09-12 trên 118 chương: 0 lệch, 0 nguồn mất, 0 thời lượng trùng
    khít nhau. Từ 09-15: trùng thời lượng **không** còn là lời phàn nàn - nó xảy ra do xác suất
    (98 chương của cuốn 2 đã có một cặp) - nên chỉ những file trùng thời lượng mới bị băm, và
    chỉ khi sha256 cũng trùng thì đó mới là chép sai chương.
    """
    complaints: list[str] = []
    before = previous_manifest(out)
    if not before:
        return 0, [f"không đọc được manifest ở {out}"]
    if not shutil.which("ffprobe"):
        return 0, ["không có `ffprobe` trong PATH - không kiểm được thời lượng"]
    durations: dict[float, list[str]] = {}
    checked = 0
    for title, item in sorted(before.items()):
        destination = out / str(item.get("file") or "")
        source = (
            VERSIONS
            / str(item.get("version") or "")
            / str(item.get("project") or "")
            / "output"
            / "chapters"
            / str(item.get("source_file") or "")
        )
        if not destination.is_file():
            complaints.append(f"chương {title}: thiếu {destination.name} trong sách")
            continue
        if not source.is_file():
            complaints.append(f"chương {title}: project gốc không còn {source.name}")
            continue
        here, there = probe_audio(destination), probe_audio(source)
        if here is None or there is None:
            complaints.append(f"chương {title}: không đo được thời lượng")
            continue
        checked += 1
        if abs(here[0] - there[0]) > 0.05:
            complaints.append(
                f"chương {title}: {here[0]:.2f}s trong sách so với {there[0]:.2f}s ở project"
            )
        if here[1:] != there[1:]:
            complaints.append(f"chương {title}: {here[1:]} kênh/tần số, project có {there[1:]}")
        durations.setdefault(round(here[0], 2), []).append(title)
    for _duration, titles in sorted(durations.items()):
        if len(titles) < 2:
            continue
        # Trùng thời lượng KHÔNG phải bằng chứng chép sai - và đây là báo động giả đầu tiên
        # nó gây ra: 09-15 09:49, sách cuốn 2 có 98 chương và cặp 050/086 trùng khít ở 0,01
        # giây. Hai file cùng 9.476.447 byte (MP3 CBR cùng thời lượng thì cùng cỡ) nhưng
        # **khác sha256**, khác `source_file`, và hai chương nguồn khác nhau hẳn (6.760 so với
        # 6.708 ký tự). Với 915 chương ~6 phút, trùng ở mức 10 ms là chuyện xác suất, không
        # phải chuyện lỗi - cứ để nguyên thì lời phàn nàn này kêu suốt và người đọc học cách
        # bỏ qua nó, đúng lúc nó cần được tin.
        #
        # Nên hỏi thêm một câu, và chỉ hỏi cho những file đã trùng: **nội dung có giống nhau
        # không?** Băm cả file, nhưng chỉ vài file trong một cặp - không phải cả sách, đúng
        # lý do docstring nêu khi từ chối băm toàn bộ.
        digests: dict[str, list[str]] = {}
        for title in titles:
            path = out / str(before[title].get("file") or "")
            try:
                digests.setdefault(sha256_file(path), []).append(title)
            except OSError:
                complaints.append(f"chương {title}: không đọc được để băm kiểm trùng")
        for digest, same in sorted(digests.items()):
            if len(same) > 1:
                complaints.append(
                    f"CHÉP SAI CHƯƠNG: {', '.join(same)} là cùng một file "
                    f"(sha {digest[:12]}…) - một chương đang nằm ở hai chỗ"
                )
    return checked, complaints


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
    """Mọi file `.txt` trong thư mục nguồn là một chương. Không hỏi nó có phải truyện không.

    Ngày 2026-09-16 tôi đã dựng một cơ chế loại trừ (`not_a_chapter.txt` cạnh nguồn) sau khi
    thấy `000.txt` của cuốn 1 là một bài về ảnh fan art dài 183 byte và đã thành một chương
    audio 6 giây. **Chủ sách gỡ bỏ nó cùng ngày**, nguyên văn: *"chương có phải nội dung sách
    để đọc hay không không phải vấn đề mà project này cần xử lý, ném vào là nó đọc thôi."*

    Doanh nghĩa ấy rõ và có lý: cái gì nằm trong thư mục nguồn là cái người ta muốn đọc, và một
    cơ chế đoán xem file nào "đáng đọc" là một cơ chế sẽ bỏ sót hoặc bỏ oan. Nên hàm này đếm
    **mọi** file, và ai không muốn một file được đọc thì lấy nó ra khỏi thư mục nguồn.
    """
    if not SOURCE.is_dir():
        return []
    return sorted(path.stem for path in SOURCE.glob("*.txt"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=BOOK)
    parser.add_argument("--apply", action="store_true", help="Chép thật thay vì chỉ liệt kê")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Chỉ kiểm cuốn sách đã ghép so với manifest (chỉ đọc), rồi thoát",
    )
    parser.add_argument(
        "--album",
        default=DEFAULT_ALBUM,
        help=f"Tên đĩa ghi vào mọi chương (mặc định {DEFAULT_ALBUM!r}; tên thật của truyện"
        " không có ở đâu trong dữ liệu)",
    )
    args = parser.parse_args(argv)

    if args.verify:
        checked, complaints = verify(args.out)
        _say(f"kiểm {checked} chương của {args.out} so với manifest:")
        for line in complaints:
            _say(f"  {line}")
        if not complaints:
            _say("  không có gì lệch: đúng thời lượng, đúng kênh/tần số, không trùng khít.")
        return 1 if complaints else 0

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
        # Lời nhắc này chỉ đúng khi tên đĩa vẫn là chỗ giữ chỗ cũ. Từ 01:40 ngày 2026-09-16
        # `DEFAULT_ALBUM` là tên THẬT (tra từ internet, đặt trong `book_paths`), nên so với
        # `DEFAULT_ALBUM` là in ra lời nhắc sai mỗi lần ghép đúng.
        if str(args.album) == PLACEHOLDER_ALBUM:
            _say('  (tên đĩa đang là chỗ giữ chỗ; đặt tên thật bằng --album "Tên truyện"'
                 " hoặc EBOOK_ALBUM)")
    _say(f"Gốc gác từng chương ghi ở {path.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
