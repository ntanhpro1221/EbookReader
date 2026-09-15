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


def tag_of(batch: int) -> str:
    """Tên phiên bản của một lô: `v0.3.0-lo01`. Các thư mục vá / đúc lại thêm `v` / `r` phía sau."""
    return f"{TAG_PREFIX}-lo{int(batch):02d}"


def describe() -> str:
    return (
        f"cuốn: root={AUDIOBOOKS_ROOT} tag={TAG_PREFIX} nguồn={SOURCE_DIR} kế hoạch={PLAN}"
        f" đĩa={ALBUM!r}"
        + (f" tôi={FIRST_PERSON!r}" if FIRST_PERSON else "")
    )


if __name__ == "__main__":
    print(describe())
