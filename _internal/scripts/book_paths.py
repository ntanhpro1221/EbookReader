"""Gốc của CUỐN SÁCH đang sản xuất — một chỗ duy nhất, đọc từ biến môi trường.

    EBOOK_AUDIOBOOKS_ROOT   thư mục chứa `_versions/` và `_book/` của cuốn      mặc định D:/Novels/Audiobooks/book2
    EBOOK_TAG_PREFIX        tiền tố tag git / tên phiên bản (`<prefix>-loNN`)    mặc định v0.3.0
    EBOOK_SOURCE_DIR        thư mục nguồn .txt                                   mặc định D:/Novels/Ebook Reader/Text_Tmp
    EBOOK_PLAN              kế hoạch lô (bảng `| lô | 000..048 | ...`)           mặc định docs/PRODUCTION_PLAN_book2.md
    EBOOK_ALBUM             tên đĩa ghi vào thẻ ID3 của mọi chương                mặc định Throne of Magical Arcana
    EBOOK_FIRST_PERSON      "tôi" trong cuốn này là ai (rỗng = kể ngôi thứ ba)   mặc định rỗng

Vì sao có file này (2026-09-13, 22:25–23:30): thư mục nguồn của cuốn 1 (`D:\\Novels\\Tools\\Text`, 478
chương) bị xoá giữa lô 10, và chủ sách chỉ sang một cuốn khác — `Text_Tmp`, 915 chương, không
chung một byte với cuốn cũ. Mười ba script đang cột chặt vào `D:/Novels/Audiobooks/_versions`,
`_book`, `v0.2.0-lo` và `PRODUCTION_PLAN.md` của cuốn 1, chép tay ở mười ba chỗ. Chủ sách đã dặn
từ trước: *"nhỡ sách khác cũng gặp chuyện thế này thì project phải tự xử lý được chứ?"* — đây là
câu trả lời: gốc sách là **tham số**, và mọi script hỏi cùng một chỗ.

Mặc định là cuốn ĐANG chạy (cuốn 2), không phải cuốn cũ: một lệnh quên đặt biến môi trường
phải rơi vào cuốn đang sản xuất, chứ không rơi vào một cuốn đã dừng. Muốn quay lại cuốn 1 (253
chương đã ghép, nguồn đang nằm trong Thùng rác) thì `source scripts/book1.env` trước khi gọi.

Cuốn 1 giữ nguyên tại chỗ: `D:/Novels/Audiobooks/_versions`, `_book`, tag `v0.2.0-lo*`, fixture
`_fixtures/*` (đường dẫn wav tuyệt đối vào cuốn 1) — không dời gì, nên không có gì để hỏng.

Script chạy trực tiếp (`python scripts/x.py`) import được `book_paths` vì thư mục `scripts/` là
`sys.path[0]`; test import theo gói (`scripts.book_paths`). Cả hai đường đều phải sống, nên mỗi
script import theo mẫu:

    try:
        from scripts.book_paths import BOOK, VERSIONS, TAG_PREFIX
    except ImportError:
        from book_paths import BOOK, VERSIONS, TAG_PREFIX
"""
from __future__ import annotations

import os
from pathlib import Path

AUDIOBOOKS_ROOT = Path(os.environ.get("EBOOK_AUDIOBOOKS_ROOT", "D:/Novels/Audiobooks/book2"))
VERSIONS = AUDIOBOOKS_ROOT / "_versions"
BOOK = AUDIOBOOKS_ROOT / "_book"
TAG_PREFIX = os.environ.get("EBOOK_TAG_PREFIX", "v0.3.0")
SOURCE_DIR = Path(os.environ.get("EBOOK_SOURCE_DIR", "D:/Novels/Ebook Reader/Text_Tmp"))
PLAN = Path(os.environ.get("EBOOK_PLAN", "docs/PRODUCTION_PLAN_book2.md"))
# Ten dia ghi vao the ID3 cua moi chuong. Thuoc ve CUON, khong thuoc ve lan ghep, va phai o
# day chu khong o `assemble_book.py`: buoc 7 cua `boundary.sh` goi `assemble_book.py --apply`
# **khong** truyen `--album`, nen mot ten dat bang tay se bi lan ghep ke tiep ghi de bang mac
# dinh. Tim ra 01:40 ngay 2026-09-16, ngay sau khi dat ten that cho ca hai cuon.
#
# Ten tra tu internet, khong tu ky uc (chu sach: *"ban phai dung internet de tra cuu chu?"*),
# va chu sach chon **ten tieng Anh**: *"khong can ten tieng viet, co ten tieng anh con tot hon"*.
#   cuon 2 = 奥术神座 / Throne of Magical Arcana (nguon la ban dich tren ln.hako.vn)
#   cuon 1 = Young Master's PoV: Woke Up As A Villain In A Game One Day  (xem scripts/book1.env)
ALBUM = os.environ.get("EBOOK_ALBUM", "Throne of Magical Arcana")
# "Tôi" trong cuốn này LÀ AI - rỗng nghĩa là cuốn kể ở ngôi thứ ba (cuốn 2), và khi rỗng thì
# không script nào truyền gì và hành vi không đổi một chút nào. Khi có, `launch_batch.sh` /
# `launch_repair.sh` truyền `--first-person` cho `cli create`, project GHI nó vào settings, và
# `character_registry.resolve_first_person_labels` gán những câu mang nhãn `tôi`/`ta`/`me` về
# đúng danh tính ấy thay vì về nhóm vô danh.
#
# Đo 04:00 ngày 2026-09-16: cuốn 1 có 129 câu như thế (ba cách viết) và tất cả là lời nhân vật
# chính; cuốn 2 có 10 câu và **cả 10 là nhật ký của một người thứ ba** - nên đây là công tắc của
# từng cuốn, không phải một luật chung.
FIRST_PERSON = os.environ.get("EBOOK_FIRST_PERSON", "")
# AI DẪN CHUYỆN, theo chương: `0=Phạm Tuyên;304=Đức Trí` nghĩa là Phạm Tuyên kể 000..303 và Đức
# Trí kể từ 304. Rỗng = cuốn không bao giờ đổi người kể (cuốn 1): không truyền gì, ở đâu cũng vậy.
#
# Chủ sách chọn Đức Trí ngày 2026-09-18 trên trang chấm giọng, sau khi nghe bản VieNeu 3.8.1:
# ranh giới 6 dừng trước khi thả lô 7 (304..343) để lô ấy mở đầu bằng người kể mới.
# `launch_batch.sh` / `launch_repair.sh` truyền `--narrator <người kể của dải>` và
# `--other-narrator <mỗi người kể KHÁC của cuốn>` cho MỌI project, cả project vá một chương cũ.
# Cả hai chiều đều cần: sau 304, người nghe đã quen Phạm Tuyên là giọng kể; còn trước 304, một
# nhân vật được trao Đức Trí sẽ mang pin ấy sang lô 7 - và nói bằng đúng giọng người kể.
#
# Giá của việc luôn truyền: settings của project mới khác project cũ, nên chạy lại một lô tạo
# TRƯỚC khi có lịch này sẽ tạo project mới thay vì mở lại. Ở ranh giới 6 điều đó không mất gì -
# bản vá khoá của cùng ranh giới đã đổi dấu vân tay, và project cũ đằng nào cũng không resume.
NARRATORS = os.environ.get("EBOOK_NARRATORS", "0=Phạm Tuyên;304=Đức Trí")


def narrator_schedule(spec: str = NARRATORS) -> list[tuple[int, str]]:
    """`0=A;304=B` -> [(0, 'A'), (304, 'B')]. Mục đầu phải bắt đầu ở chương 0."""
    schedule: list[tuple[int, str]] = []
    for part in (piece.strip() for piece in spec.split(";")):
        if not part:
            continue
        start, sep, name = part.partition("=")
        if not sep or not start.strip().isdigit() or not name.strip():
            raise ValueError(f"EBOOK_NARRATORS: mục {part!r} phải có dạng <chương>=<giọng>")
        schedule.append((int(start), name.strip()))
    if schedule:
        if schedule[0][0] != 0:
            raise ValueError("EBOOK_NARRATORS: mục đầu phải là 0=<người kể của cuốn>")
        starts = [start for start, _name in schedule]
        if starts != sorted(set(starts)):
            raise ValueError("EBOOK_NARRATORS: chương bắt đầu phải tăng dần và không trùng")
    return schedule


def narrator_args(first: int, last: int, spec: str = NARRATORS) -> list[str]:
    """Tham số `cli create` cho project đọc chương first..last (rỗng khi cuốn không có lịch).

    Một dải vắt qua chỗ đổi người kể bị TỪ CHỐI chứ không chọn giùm: một project chỉ có một người
    kể, nên nửa kia của dải sẽ đọc sai người mà không cổng nào bắt.
    """
    schedule = narrator_schedule(spec)
    if not schedule:
        return []
    index = max(i for i, (start, _name) in enumerate(schedule) if start <= int(first))
    if index + 1 < len(schedule) and schedule[index + 1][0] <= int(last):
        raise ValueError(
            f"chương {int(first):03d}..{int(last):03d} vắt qua chỗ đổi người kể ở chương "
            f"{schedule[index + 1][0]:03d} - tách thành hai dải"
        )
    current = schedule[index][1]
    args = ["--narrator", current]
    for name in dict.fromkeys(name for _start, name in schedule if name != current):
        args += ["--other-narrator", name]
    return args


def tag_of(batch: int) -> str:
    """Tên phiên bản của một lô: `v0.3.0-lo01`. Các thư mục vá / đúc lại thêm `v` / `r` phía sau."""
    return f"{TAG_PREFIX}-lo{int(batch):02d}"


def describe() -> str:
    return (
        f"cuốn: root={AUDIOBOOKS_ROOT} tag={TAG_PREFIX} nguồn={SOURCE_DIR} kế hoạch={PLAN}"
        f" đĩa={ALBUM!r}"
        + (f" tôi={FIRST_PERSON!r}" if FIRST_PERSON else "")
        + (f" người kể={NARRATORS!r}" if NARRATORS else "")
    )


def _main(argv: list[str]) -> int:
    import sys

    # `narrator-args FIRST LAST`: in mỗi tham số một dòng, UTF-8, xuống dòng kiểu Unix - shell đọc
    # bằng `mapfile -t`, và `print` trên Windows sẽ để lại `\r` dính vào tên giọng.
    if len(argv) == 3 and argv[0] == "narrator-args":
        try:
            args = narrator_args(int(argv[1]), int(argv[2]))
        except ValueError as exc:
            sys.stderr.write(f"{exc}\n")
            return 2
        sys.stdout.buffer.write("".join(f"{arg}\n" for arg in args).encode("utf-8"))
        return 0
    if argv:
        sys.stderr.write("dùng: book_paths.py [narrator-args FIRST LAST]\n")
        return 2
    print(describe())
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
