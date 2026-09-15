"""Va analysis.py + character_registry.py: mot dai tu hay mot chu mo dau cau khong phai nhan vat.

Chay: python patch_a_pronoun_is_not_a_character.py <root>

**CHI AP O RANH GIOI, TRUOC KHI MOT LO BAT DAU PHAN TICH.** Ca hai file nam trong
`ANALYSIS_CASTING_IMPLEMENTATION_FILES`: doi sau khi phan tich da bat dau thi lo ay MAT phan tich.

## Ca that

`scripts/measure_phantom_speakers.py` do tren 129 project cua ca hai cuon (565 ten nguoi noi,
17.461 cau): 87 cau thuoc ve nhung "nhan vat" khong ton tai — `Toi` 70, `Minh` 10 (+`MINH` 6),
`BA` 4, `Nghe` 4, `Giai` 2, `Tin` 1 — va rieng cuon 1 con `ME` 94 cau.

Nguon `“La toi, Victor.” Nghe giong cua Victor…` cho ra mot "nhan vat" ten `Nghe` giu 3 cau
thuc ra cua Victor va Nam tuoc Othello, gop mot va cham cung chuong o lo 3 (chuong 36), va mot
cai ten khong co gioi tinh nhu the tung chan ca cong dan giong.

## Ba phan, va phan thu ba ban dau toi viet SAI CHO

Ban dau ban va nay them mot danh sach dai tu **moi** vao `analysis.py` va tra `UNKNOWN`. Do lai
thi hoa ra du an **da co** dung khai niem ay: `character_registry.PRONOUNS` (co tu 2026-08-02)
va no duoc dung o sau cho, trong do `build_registry_and_cast` day moi dong co ten la dai tu vao
nhom vo danh thay vi cast nhu mot nhan vat. Chung cu tren du lieu:

    Toi (alpha55): KHONG co dong `characters` nao - PRONOUNS da chan dung; 33 cau doc bang
                   giong cua nhom vo danh
    ME  (lo10):    CO dong `characters`, importance='main', 54 lan nhac, va o lo08 no con
                   **chia giong voi JAKE** - vi "me" khong nam trong PRONOUNS

Nen phan thu ba dung la **mot dong trong `PRONOUNS`**, khong phai mot danh sach thu hai o file
khac. Do lai voi cac muc de xuat: dung **mot** ten trong ca kho bi chan them — `ME`, 94 cau, co
dong `characters` o 4 project. `tao`, `tui`, `to`, `chung toi`, `chung minh` khong khop gi hom
nay; chung o day de lan sau khoi phai sua lai.

`me` la tieng Anh, khong phai tieng Viet - nhung mot nhan **toan bo** la "me" thi khong bao gio
la ten nguoi trong mot cuon tieng Viet, va PRONOUNS chi so voi toan bo nhan.

## Lo im lang o `_name_candidate_key`

`_name_candidate_key(v) = v.replace("’","'").casefold()` **khong bo dau**, con
`NAME_CANDIDATE_EXCLUSIONS` viet **khong dau** ("toi", "minh", "nguoi", "khong", "tieng"...).
Do bang `scripts/measure_the_dead_exclusions.py`: 105 muc ay hom nay chan duoc **dung 2 ten**
trong ca kho (`CHA` 9 cau, `TIM` 1). Bo dau o khoa chan them dung 5 ten (`Toi`, `TOI`, `Minh`,
`MINH`, `BA`) - **ca 5 la phantom, 0 ten nhan vat that**.

Chieu nguoc: `ATTRIBUTION_SENTENCE_START_EXCLUSIONS` lai viet **co dau** ("cung", "neu"), nen
bo dau o khoa ma khong viet lai danh sach ay se **giet** no. Ban va dong nhat ve mot dang.

`TIM` cho thay cai gia cua danh sach toan cuc: `Tim` la ten nguoi Anh co that, bi chan boi muc
"tim" (tieng Viet "tim"/"tim"). Nen bon chu moi (`nghe`, `tin`, `giai`, `im`) chi vao danh sach
**mo dau cau** - dung cho loi sinh ra - khong vao danh sach toan cuc.

## Cai ban va CO Y khong lam

Do bang tay 7 ca cho thay ten nguoi noi that nam **ngay trong** cau tuong thuat bi lay chu dau
(`Nghe thay tieng on, **Othello** buoc ra…`), va "lay cai ten trong cau ay" dung 4/4 - nhung no
**khong** duoc lam thanh luat, vi danh sach loai tru co san ton tai de noi "cau nay khong neu
ten nguoi noi, dung doan". Phan vi du that, chuong 3 cuon 1: `Sau khi Benjamin lai hoi Lucien
them vai cau…` - "Sau" da nam trong danh sach, va lay "Benjamin" se gan sai mot cau cua Lucien.

Va no khong chan cac tieng xung ho ngoi thu ba (`ba`, `ong`, `cha`, `me`... tieng Viet): chung
la mot NGUOI THAT chua duoc goi ten, va du an co co che rieng cho ho (`GENERIC_SPEAKER_TRAITS` +
`NPC_LOCAL:`). Doc ca that: `BA` o chuong 21 cuon 1 la nguoi dan ba gia lam me, va 3 cau ay dung
la loi cua ba ay. Muc hang cho rieng cho ho con doi mot phep do: voi tung cau, canh ay co neu
ten nguoi noi o dau gan do khong.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])

# ---- 1 + 2: analysis.py ----------------------------------------------------------------
p = root / "ebook_reader" / "analysis.py"
s = io.open(p, encoding="utf-8").read()

OLD_KEY = '''def _name_candidate_key(value: str) -> str:
    return value.replace("’", "'").casefold()'''
NEW_KEY = '''def _name_candidate_key(value: str) -> str:
    """Khoá so tên với các danh sách loại trừ: hạ hoa-thường **và bỏ dấu**.

    Bản trước chỉ `casefold()`, trong khi `NAME_CANDIDATE_EXCLUSIONS` viết không dấu ("toi",
    "minh", "nguoi", "khong", "tieng"…) — nên những mục ấy không bao giờ khớp một tên tiếng
    Việt có dấu. Đo trên 565 tên người nói của cả hai cuốn (17.461 câu): danh sách 105 mục ấy
    chặn được **đúng hai** tên, `CHA` và `TIM`. Bỏ dấu ở đây chặn thêm đúng năm tên — `Tôi`,
    `TÔI`, `Mình`, `MÌNH`, `BÀ` — và **cả năm là người không tồn tại**, không một tên nhân vật
    thật nào (`scripts/measure_the_dead_exclusions.py`).

    `ATTRIBUTION_SENTENCE_START_EXCLUSIONS` vì thế được viết lại dạng bỏ dấu: nó vốn viết CÓ
    dấu, nên phép gộp này sẽ giết nó nếu để nguyên.
    """
    lowered = value.replace("’", "'").casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in decomposed if not unicodedata.combining(char))'''
assert s.count(OLD_KEY) == 1, "khong khop _name_candidate_key"
s = s.replace(OLD_KEY, NEW_KEY, 1)

OLD_STARTS = '''ATTRIBUTION_SENTENCE_START_EXCLUSIONS = {
    "ban", "cùng", "dù", "khi", "lúc", "nếu", "ngoài", "sau", "suy", "thay",
    "theo", "trong", "trước", "tuy", "vì",
}'''
NEW_STARTS = '''# Khoá của `_name_candidate_key` bỏ dấu từ 2026-09-15, nên danh sách này viết dạng bỏ dấu.
# Viết có dấu như trước là viết một danh sách không bao giờ khớp.
#
# Bốn mục cuối là ca thật: `Nghe`, `Tin`, `Giai`, `Im` từng thành "nhân vật" vì chúng mở một
# câu tường thuật ngay sau dấu đóng ngoặc kép và `_leading_proper_name` lấy chữ đầu ấy làm tên
# (8 câu trong hai cuốn; `Nghe` giữ 3 câu của Victor và Othello, và góp một va chạm cùng chương
# ở lô 3). Đã kiểm trên 565 tên người nói: không tên nhân vật thật nào có từ đầu bỏ dấu trùng
# bốn mục này. Chúng **chỉ** vào danh sách mở-đầu-câu, không vào `NAME_CANDIDATE_EXCLUSIONS`:
# mục "tim" trong danh sách toàn cục đã chặn mất `Tim`, một tên người Anh có thật.
ATTRIBUTION_SENTENCE_START_EXCLUSIONS = {
    "ban", "cung", "du", "khi", "luc", "neu", "ngoai", "sau", "suy", "thay",
    "theo", "trong", "truoc", "tuy", "vi",
    "giai", "im", "nghe", "tin",
}'''
assert s.count(OLD_STARTS) == 1, "khong khop ATTRIBUTION_SENTENCE_START_EXCLUSIONS"
s = s.replace(OLD_STARTS, NEW_STARTS, 1)

assert "import unicodedata" in s, "analysis.py phai da import unicodedata"
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

# ---- 3: character_registry.py --------------------------------------------------------
q = root / "ebook_reader" / "character_registry.py"
t = io.open(q, encoding="utf-8").read()

OLD_PRONOUNS = '''PRONOUNS = {
    "hắn", "nàng", "cô ấy", "anh ấy", "ông ấy", "bà ấy", "người đó", "kẻ đó",
    "ta", "tôi", "mình", "chúng ta", "bọn họ",
}'''
NEW_PRONOUNS = '''# Một đại từ không phải một nhân vật: `build_registry_and_cast` đẩy mọi dòng có tên là đại từ
# vào nhóm vô danh thay vì cast như một người. Nó làm việc ấy đúng - `Tôi` ở alpha55 **không**
# có dòng `characters` nào, 33 câu của nó đọc bằng giọng nhóm vô danh.
#
# `me` thêm vào 2026-09-15 vì đúng cái lỗ ấy: cuốn 1 kể ở ngôi thứ nhất và mô hình khai người
# nói là `ME` (tiếng Anh) cho **94 câu** thoại của chính nhân vật chính. "me" không nằm ở đây
# nên `ME` thành một nhân vật đầy đủ - `characters` có dòng riêng, `importance='main'`, 54 lần
# nhắc - và ở lô 8 nó còn **chia giọng với JAKE**. Đo trên cả hai cuốn: thêm những mục dưới đây
# chặn đúng **một** cái tên, `ME`; `tao`, `tui`, `tớ`, `chúng tôi`, `chúng mình` không khớp gì
# hôm nay và ở đây để lần sau khỏi phải sửa lại.
#
# `me` là tiếng Anh, nhưng một nhãn **toàn bộ** là "me" thì không bao giờ là tên người trong một
# cuốn tiếng Việt, và phép so này chỉ so với toàn bộ nhãn (`normalize_name`).
#
# Tiếng xưng hô ngôi thứ ba tiếng Việt (`bà`, `ông`, `cha`, `mẹ`) **không** ở đây: chúng là một
# NGƯỜI THẬT chưa được gọi tên - đọc ca thật, `BÀ` ở chương 21 cuốn 1 là người đàn bà giả làm
# mẹ và 3 câu ấy đúng là lời của bà - nên chỗ của chúng là `GENERIC_SPEAKER_TRAITS` +
# `NPC_LOCAL:`, sau một phép đo còn thiếu (xem docs/OPTIMISATION_QUEUE.md).
PRONOUNS = {
    "hắn", "nàng", "cô ấy", "anh ấy", "ông ấy", "bà ấy", "người đó", "kẻ đó",
    "ta", "tôi", "mình", "chúng ta", "bọn họ",
    "me", "tao", "tui", "tớ", "chúng tôi", "chúng mình",
}'''
assert t.count(OLD_PRONOUNS) == 1, "khong khop PRONOUNS"
t = t.replace(OLD_PRONOUNS, NEW_PRONOUNS, 1)
io.open(q, "w", encoding="utf-8", newline="\n").write(t)
print(f"da va {q}")

TEST = '''"""Một đại từ hay một chữ mở đầu câu tường thuật không phải một nhân vật.

Đo trên 129 project của cả hai cuốn (565 tên người nói, 17.461 câu): 87 câu thuộc về những
"nhân vật" không tồn tại — `Tôi` 70, `Mình` 10 (+`MÌNH` 6), `BÀ` 4, `Nghe` 4, `Giai` 2, `Tin` 1
— và riêng cuốn 1 còn `ME` **94 câu**.

Hai đường sinh, và mỗi đường một chỗ sửa:

- `_leading_proper_name` lấy chữ hoa đầu của câu tường thuật ngay sau dấu đóng ngoặc kép. Mẫu
  của nó chỉ nhận ASCII, nên nó sinh được đúng `Nghe`, `Tin`, `Giai`, `Im`. Hàm ấy **đã** có bộ
  canh (`ATTRIBUTION_SENTENCE_START_EXCLUSIONS`); nó chỉ thiếu bốn chữ, và thiếu vì khoá so
  không bỏ dấu trong khi danh sách bên cạnh viết không dấu.
- Tên **do mô hình khai** đi qua `character_registry.PRONOUNS`, thứ đã có từ 2026-08-02 và làm
  việc đúng: `Tôi` ở alpha55 không có dòng `characters` nào. Lỗ là "me" không nằm trong đó, nên
  `ME` thành một nhân vật `importance='main'` và ở lô 8 chia giọng với JAKE.
"""
from __future__ import annotations

from ebook_reader.analysis import (
    ATTRIBUTION_SENTENCE_START_EXCLUSIONS,
    NAME_CANDIDATE_EXCLUSIONS,
    _leading_proper_name,
    _name_candidate_key,
)
from ebook_reader.character_registry import PRONOUNS, normalize_name


def test_the_key_folds_the_marks_so_the_lists_can_match() -> None:
    assert _name_candidate_key("T\\u00f4i") == "toi"
    assert _name_candidate_key("M\\u00ecnh") == "minh"
    assert _name_candidate_key("B\\u00c0") == "ba"
    assert _name_candidate_key("\\u0110\\u1ee8C") == "duc"
    assert _name_candidate_key("Lucien") == "lucien"


def test_both_exclusion_lists_are_written_folded() -> None:
    """Viết có dấu là viết một danh sách không bao giờ khớp - khoá đã bỏ dấu."""
    for entry in ATTRIBUTION_SENTENCE_START_EXCLUSIONS:
        assert _name_candidate_key(entry) == entry, entry
    for entry in NAME_CANDIDATE_EXCLUSIONS:
        assert _name_candidate_key(entry) == entry, entry


def test_the_narration_word_that_stole_three_lines_is_refused() -> None:
    """Ca thật: `Nghe gi\\u1ecdng c\\u1ee7a Victor…` ngay sau `“L\\u00e0 t\\u00f4i, Victor.”`."""
    assert _leading_proper_name("Nghe gi\\u1ecdng c\\u1ee7a Victor b\\u00e2y gi\\u1edd nh\\u1eb9 h\\u01a1n.") is None
    assert _leading_proper_name("Tin nh\\u1eafn vi\\u1ebft nh\\u01b0 sau.") is None
    assert _leading_proper_name("Giai \\u0111i\\u1ec7u \\u1ea5y l\\u1eb7p l\\u1ea1i m\\u1ed9t l\\u1ea7n n\\u1eefa.") is None
    assert _leading_proper_name("Im l\\u1eb7ng m\\u1ed9t l\\u00fac l\\u00e2u.") is None


def test_a_real_name_opening_the_same_sentence_still_works() -> None:
    """Bộ canh chỉ được bớt tên bịa, không được bớt tên thật."""
    assert _leading_proper_name("Victor gi\\u1ea3i th\\u00edch th\\u00eam m\\u1ed9t l\\u1ea7n n\\u1eefa.") == "Victor"
    assert _leading_proper_name("Othello b\\u01b0\\u1edbc ra kh\\u1ecfi v\\u0103n ph\\u00f2ng.") == "Othello"


def test_the_english_first_person_label_is_a_pronoun_too() -> None:
    """94 câu thoại của nhân vật chính cuốn 1 mang nhãn `ME`, và nó thành một nhân vật thật."""
    assert normalize_name("ME") in PRONOUNS
    assert normalize_name("Me") in PRONOUNS


def test_the_pronouns_that_were_already_right_stay_right() -> None:
    for name in ("T\\u00f4i", "T\\u00d4I", "M\\u00ecnh", "ta", "H\\u1eafn", "n\\u00e0ng"):
        assert normalize_name(name) in PRONOUNS, name


def test_a_real_name_is_not_a_pronoun() -> None:
    for name in ("Lucien", "NG\\u01af\\u1edcI TR\\u1ea2 L\\u1edcI", "Tim", "Anh Tu\\u1ea5n", "M\\u1ecd"):
        assert normalize_name(name) not in PRONOUNS, name


def test_a_vietnamese_kinship_label_is_left_for_its_own_measurement() -> None:
    """`BÀ` là một người thật chưa được gọi tên; chỗ của nó là nhãn chung chung, không phải đây."""
    for name in ("B\\u00c0", "\\u00d4ng", "CHA", "M\\u1eb8"):
        assert normalize_name(name) not in PRONOUNS, name
'''
u = root / "tests" / "test_a_pronoun_is_not_a_character.py"
io.open(u, "w", encoding="utf-8", newline="\n").write(TEST)
print(f"da tao {u}")
