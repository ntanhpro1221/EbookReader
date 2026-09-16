"""Một nhãn không có trong nguồn thì không được giữ một giọng — và `NARRATOR` là ngoại lệ.

Kho giọng của cuốn 2 đã cấp hết (nam 14/14), nên mỗi pin là một chỗ. Đo 09:45 ngày 2026-09-16:
**sáu nhãn** đang giữ pin trong khi chuỗi của chúng **không hề xuất hiện** trong nguồn —
`SELNE` (32 lần nhắc; `Selne` 0 lần / `Selene` 198 lần), `SAMAELE` (`Samaele` 0 / `Samael` 1.375),
`ALICE DRACEN` (`Alice` 219 / `Dracen` 0), `NATHASA`, `NATHANAS`. Chúng sống qua 12–21 project vì
`port_casting` mang pin theo danh tính, nên một lần mô hình gõ sai là một chỗ mất không, mãi mãi.

Phép kiểm cố ý **nhị phân**: chỉ hỏi "chuỗi này có tồn tại trong văn bản không", không đoán ai là
ai. Luật mạnh hơn — "gộp về cái tên gần nhất" — đã bị chính phép đo bác bỏ
(`scripts/measure_would_a_name_fold_be_safe.py`: 47 cặp ở cuốn 2 và phần lớn sai; `JOEL` về
`JOHN`, `AARON` về `SHARON`, `ATHY` về phantom `TAY`). Nên ở đây không gộp ai với ai: chỉ thôi
ghim, và bỏ pin đã có.

Hai cái bẫy mà bài này ghim lại, vì cả hai đã xảy ra thật khi viết:

1. **`NARRATOR` không có trong nguồn** — hiển nhiên. Bản đầu của phép kiểm in ra
   `BỎ PIN NARRATOR: narrator`; một lượt `--apply` như thế sẽ đúc lại giọng kể của cả cuốn sách.
2. **Phải bỏ dấu cả hai bên.** Nhãn `NGUOI TRA LOI` (160 lần nhắc, có pin) là bản rơi dấu của
   `NGƯỜI TRẢ LỜI` trong nguồn; so nguyên dấu thì nó bị gắn cờ oan.
"""
from __future__ import annotations

from pathlib import Path

from scripts.pin_the_book_cast import names_absent_from_the_source

NAMES = [
    "SELENE",          # có trong nguồn
    "SELNE",           # KHÔNG - gõ sai
    "ALICE DRACEN",    # KHÔNG - họ bịa, dù `Alice` có trong nguồn
    "NARRATOR",        # tên dành riêng, không bao giờ bị hỏi
    "UNKNOWN",         # như trên
    "NGUOI TRA LOI",   # rơi dấu: nguồn viết `NGƯỜI TRẢ LỜI`
    "TỬ TƯỚC CARENDIA",  # nhãn tiếng Việt - không phải chữ La-tinh, giữ hành vi cũ
    "NPC_LOCAL::c00001::rabc::áo xanh",  # phạm vi cục bộ
    "ANONYMOUS_MALE_1",
]


def _source(tmp_path: Path) -> Path:
    folder = tmp_path / "Text"
    folder.mkdir()
    (folder / "001.txt").write_text(
        "Selene bước vào. Alice nhìn theo.\n"
        "NGƯỜI TRẢ LỜI nói một câu.\n"
        "Tử tước Carendia đứng đó.\n",
        encoding="utf-8",
    )
    return folder


def test_only_the_labels_that_do_not_exist_come_back(tmp_path: Path) -> None:
    absent = names_absent_from_the_source(NAMES, source=_source(tmp_path))

    assert absent == {"SELNE", "ALICE DRACEN"}


def test_the_narrator_is_never_flagged(tmp_path: Path) -> None:
    """Ca thật: bản đầu in `BỎ PIN NARRATOR: narrator` trên project lô 4."""
    absent = names_absent_from_the_source(["NARRATOR", "UNKNOWN"], source=_source(tmp_path))

    assert absent == set()


def test_a_dropped_diacritic_label_is_not_flagged(tmp_path: Path) -> None:
    absent = names_absent_from_the_source(["NGUOI TRA LOI"], source=_source(tmp_path))

    assert absent == set(), "so sánh phải bỏ dấu cả hai bên"


def test_a_missing_source_directory_flags_nothing(tmp_path: Path) -> None:
    """Không đọc được nguồn thì không được kết tội ai - im lặng bỏ qua là hành vi đúng."""
    assert names_absent_from_the_source(NAMES, source=tmp_path / "khong-co") == set()


def test_a_name_inside_a_longer_word_does_not_count(tmp_path: Path) -> None:
    """`ALI` không được coi là "có trong nguồn" chỉ vì `Alice` chứa nó."""
    absent = names_absent_from_the_source(["ALI"], source=_source(tmp_path))

    assert absent == {"ALI"}
