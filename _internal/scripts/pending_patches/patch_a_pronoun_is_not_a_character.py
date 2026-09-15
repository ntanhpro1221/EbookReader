"""Va analysis.py: mot dai tu hay mot chu mo dau cau khong phai mot nhan vat.

Chay: python patch_a_pronoun_is_not_a_character.py <root>

**CHI AP O RANH GIOI, TRUOC KHI MOT LO BAT DAU PHAN TICH.** `analysis.py` nam trong
`ANALYSIS_CASTING_IMPLEMENTATION_FILES`: doi sau khi phan tich da bat dau thi lo ay MAT phan tich.

## Ca that va so lieu

`scripts/measure_phantom_speakers.py` do tren 129 project cua ca hai cuon (565 ten nguoi noi,
17.461 cau): **87 cau** thuoc ve nam "nhan vat" khong ton tai.

    Toi 70 cau   Minh 10 (+ MINH 6)   BA 4   Nghe 4   Giai 2   Tin 1

Nguon `“La toi, Victor.” Nghe giong cua Victor…` cho ra mot "nhan vat" ten `Nghe` giu 3 cau
thuc ra cua Victor va Nam tuoc Othello; no con gop mot va cham cung chuong o lo 3 (chuong 36,
chia giong voi Camil), va mot cai ten khong co gioi tinh nhu the tung chan ca cong dan giong.
Va no da toi audio: `Toi` co `voice_profiles` rieng (`preset_thai_son_f104_p+00`, locked) doc
**33 cau trong 5 chuong** cua cuon 1.

## Hai duong sinh, doc tu chinh ma chu khong doan

1. `_leading_proper_name` lay chu hoa dau cua cau tuong thuat ngay sau dau dong ngoac kep, va
   no khop bang `LATIN_PROPER_NAME_SURFACE_PATTERN` = `[A-Z][A-Za-z]*…` — **chi ASCII**. Nen
   duong nay sinh duoc dung `Nghe`, `Tin`, `Giai`, `Im` (8 cau). Ham ay DA co bo canh
   (`ATTRIBUTION_SENTENCE_START_EXCLUSIONS`); chi thieu bon chu.

2. `speaker` **do mo hinh tu khai** di thang vao hang qua `_canonical_speaker`, khong mot phep
   kiem nao hoi "cai nay co phai ten nguoi khong". `Toi`, `Minh`, `BA` (79 cau) den tu day.

## Mot lo im lang nam ngay canh

`_name_candidate_key(v) = v.replace("’","'").casefold()` **khong bo dau**, con
`NAME_CANDIDATE_EXCLUSIONS` viet **khong dau** ("toi", "minh", "nguoi", "khong", "tieng"...).
Do bang `scripts/measure_the_dead_exclusions.py`: 105 muc ay hom nay chan duoc **dung hai**
ten trong ca kho — `CHA` (9 cau) va `TIM` (1). Bo dau o khoa chan them dung nam ten (`Toi`,
`TOI`, `Minh`, `MINH`, `BA`), **ca nam la phantom, 0 ten nhan vat that**.

Chieu nguoc lai: `ATTRIBUTION_SENTENCE_START_EXCLUSIONS` lai viet **co dau** ("cung", "neu"),
nen bo dau o khoa ma khong viet lai danh sach ay se **giet** no. Ban va dong nhat ve mot dang.

`TIM` cho thay cai gia cua danh sach toan cuc: `Tim` la ten nguoi Anh co that, bi chan boi muc
"tim" (tieng Viet "tim"/"tim"). Nen bon chu moi chi vao danh sach **mo dau cau** — cho loi sinh
ra — khong vao danh sach toan cuc.

## Hai dieu ban va CO Y khong lam

- **Khong lay "cai ten nam trong cau tuong thuat"** du do bang tay 7 ca cho thay no dung 4/4
  (`Nghe thay tieng on, **Othello** buoc ra…`). Danh sach loai tru co san ton tai de noi "cau
  nay khong neu ten nguoi noi, dung doan", va co phan vi du that: chuong 3 cuon 1, `Sau khi
  Benjamin lai hoi Lucien them vai cau…` — "Sau" da nam trong danh sach, va lay "Benjamin"
  trong cau ay se gan sai mot cau thoai cua Lucien. Bo ten phantom roi de **chuoi sua da co**
  (`_apply_explicit_attribution`, khoa doan, khoa thoai tiep dien) quyet.

- **Khong chan cac tieng xung ho ngoi thu ba** (`ba`, `ong`, `co`, `anh`, `em`, `chi`, `con`):
  chung la ten nguoi that duoc (`Anh`, `Em` la ten nguoi Viet thuong gap), va du an da co co
  che rieng cho nhan chung chung co gioi tinh/tuoi (`GENERIC_SPEAKER_TRAITS` +
  `NPC_LOCAL:`). Danh sach o day chi gom **dai tu ngoi thu nhat**, thu khong bao gio goi ten
  mot nguoi khac. `BA` (4 cau) vi the con lai; no thuoc ve mot phep do khac, tren chinh 4 cau ay.
  Cung ly do ay ma "may" khong co trong danh sach: `May` la mot ten tieng Anh, va
  `CMUDICT_CONTEXT_ONLY` da ghi dung su lung chung ay.

`UNKNOWN` la duong da di nhieu: 2.214 cau trong kho dang o do, va no nam trong
`RESERVED_SPEAKERS`, nen tra ve no khong mo mot loi moi nao.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "analysis.py"
s = io.open(p, encoding="utf-8").read()

OLD_KEY = '''def _name_candidate_key(value: str) -> str:
    return value.replace("’", "'").casefold()'''
NEW_KEY = '''def _name_candidate_key(value: str) -> str:
    """Khoá so tên với các danh sách loại trừ: hạ hoa-thường **và bỏ dấu**.

    Bản trước chỉ `casefold()`, trong khi `NAME_CANDIDATE_EXCLUSIONS` viết không dấu ("toi",
    "minh", "nguoi", "khong", "tieng"…) — nên những mục ấy không bao giờ khớp một tên tiếng
    Việt có dấu. Đo trên 565 tên người nói của cả hai cuốn (17.461 câu): danh sách 105 mục ấy
    chặn được **đúng hai** tên, `CHA` và `TIM`. Bỏ dấu ở đây chặn thêm đúng năm tên — `Tôi`
    (70 câu), `TÔI`, `Mình` (10), `MÌNH` (6), `BÀ` (4) — và **cả năm là người không tồn tại**,
    không một tên nhân vật thật nào (`scripts/measure_the_dead_exclusions.py`).

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
# (8 câu trong hai cuốn). Đã kiểm trên 565 tên người nói: không tên nhân vật thật nào có từ
# đầu bỏ dấu trùng bốn mục này.
ATTRIBUTION_SENTENCE_START_EXCLUSIONS = {
    "ban", "cung", "du", "khi", "luc", "neu", "ngoai", "sau", "suy", "thay",
    "theo", "trong", "truoc", "tuy", "vi",
    "giai", "im", "nghe", "tin",
}
# Một đại từ ngôi thứ nhất không phải một nhân vật. Mô hình tự khai tên người nói và không có
# phép kiểm nào hỏi lại, nên `Tôi` (70 câu) đã thành nhân vật có `voice_profiles` khoá và đọc
# 33 câu trong 5 chương của cuốn 1, còn `Mình` giữ 16 câu — những trang ghi chép của người khác
# đọc lên.
#
# Chỉ đại từ **ngôi thứ nhất**, thứ không bao giờ gọi tên một người khác. Những tiếng xưng hô
# ngôi thứ ba (`bà`, `ông`, `cô`, `anh`, `em`) không nằm ở đây: chúng là tên người thật được
# (`Anh`, `Em` là tên người Việt thường gặp), và dự án đã có cơ chế riêng cho nhãn chung chung
# có giới tính/tuổi (`GENERIC_SPEAKER_TRAITS` + `NPC_LOCAL:`). Cùng lý do ấy mà "may" không có
# trong danh sách: `May` là một tên tiếng Anh, đúng sự lửng lơ mà `CMUDICT_CONTEXT_ONLY` ghi.
#
# Chỉ khớp **toàn bộ** tên, không khớp từ đầu: `NGƯỜI TRẢ LỜI` (2.168 câu) và `BA TƯỚC ELEIJAH`
# là tên thật nhiều từ.
FIRST_PERSON_SPEAKER_EXCLUSIONS = {
    "toi", "minh", "ta", "tao", "tui", "chung toi", "chung ta", "chung minh",
}'''
assert s.count(OLD_STARTS) == 1, "khong khop ATTRIBUTION_SENTENCE_START_EXCLUSIONS"
s = s.replace(OLD_STARTS, NEW_STARTS, 1)

OLD_MODEL_SPEAKER = '''        speaker = _canonical_speaker(item.get("speaker"))'''
NEW_MODEL_SPEAKER = '''        speaker = _speaker_that_is_not_a_pronoun(item.get("speaker"))'''
assert s.count(OLD_MODEL_SPEAKER) == 1, "khong khop cho lay speaker cua mo hinh"
s = s.replace(OLD_MODEL_SPEAKER, NEW_MODEL_SPEAKER, 1)

OLD_HELPER_ANCHOR = '''def is_local_speaker(value: Any) -> bool:'''
NEW_HELPER_ANCHOR = '''def _speaker_that_is_not_a_pronoun(value: Any) -> str:
    """Tên người nói do mô hình khai, sau khi bỏ những cái tên chỉ là một đại từ ngôi thứ nhất.

    Không có phép kiểm nào hỏi lại mô hình về cái tên nó khai, nên `Tôi` đã thành một nhân vật
    có `voice_profiles` riêng và đọc 33 câu trong 5 chương của cuốn 1; `Mình` giữ 16 câu.
    Tổng 87 câu trong hai cuốn (`scripts/measure_phantom_speakers.py`).

    Trả `UNKNOWN` thay vì đoán một người chủ: chuỗi sửa có sẵn (`_apply_explicit_attribution`,
    khoá đoạn, khoá thoại tiếp diễn) là chỗ quyết ai nói, và một cái tên trông hợp lệ chính là
    thứ làm chuỗi ấy không bao giờ chạy. `UNKNOWN` là đường đã đi nhiều: 2.214 câu trong kho
    đang ở đó, và nó nằm trong `RESERVED_SPEAKERS`.
    """
    speaker = _canonical_speaker(value)
    if _name_candidate_key(speaker) in FIRST_PERSON_SPEAKER_EXCLUSIONS:
        return "UNKNOWN"
    return speaker


def is_local_speaker(value: Any) -> bool:'''
assert s.count(OLD_HELPER_ANCHOR) == 1, "khong khop cho dat ham moi"
s = s.replace(OLD_HELPER_ANCHOR, NEW_HELPER_ANCHOR, 1)

assert "import unicodedata" in s, "analysis.py phai da import unicodedata"
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

TEST = '''"""Một đại từ hay một chữ mở đầu câu tường thuật không phải một nhân vật.

Đo trên 129 project của cả hai cuốn (565 tên người nói, 17.461 câu): **87 câu** thuộc về năm
"nhân vật" không tồn tại — `Tôi` 70, `Mình` 10 (+`MÌNH` 6), `BÀ` 4, `Nghe` 4, `Giai` 2, `Tin` 1.
Nguồn `“Là tôi, Victor.” Nghe giọng của Victor…` cho ra một nhân vật tên `Nghe` giữ 3 câu thực
ra của Victor và Nam tước Othello, và `Tôi` có một `voice_profiles` khoá riêng đọc 33 câu trong
5 chương của cuốn 1.

Hai đường sinh: `_leading_proper_name` lấy chữ hoa đầu của câu tường thuật sau dấu đóng ngoặc
kép (chỉ ASCII được, nên đúng `Nghe`/`Tin`/`Giai`/`Im`), và `speaker` do mô hình tự khai đi
thẳng vào hàng (`Tôi`/`Mình`/`BÀ`). Bài này khoá cả hai, và khoá cả cái lỗ im lặng bên cạnh:
`_name_candidate_key` không bỏ dấu nên 105 mục của `NAME_CANDIDATE_EXCLUSIONS` chỉ chặn được
đúng hai tên trong cả kho.
"""
from __future__ import annotations

from ebook_reader.analysis import (
    ATTRIBUTION_SENTENCE_START_EXCLUSIONS,
    FIRST_PERSON_SPEAKER_EXCLUSIONS,
    NAME_CANDIDATE_EXCLUSIONS,
    _leading_proper_name,
    _name_candidate_key,
    _speaker_that_is_not_a_pronoun,
)


def test_the_key_folds_the_marks_so_the_lists_can_match() -> None:
    assert _name_candidate_key("T\\u00f4i") == "toi"
    assert _name_candidate_key("M\\u00ecnh") == "minh"
    assert _name_candidate_key("B\\u00c0") == "ba"
    assert _name_candidate_key("\\u0110\\u1ee8C") == "duc"
    assert _name_candidate_key("Lucien") == "lucien"


def test_the_sentence_start_list_is_written_folded() -> None:
    """Viết có dấu là viết một danh sách không bao giờ khớp - khoá đã bỏ dấu."""
    for entry in ATTRIBUTION_SENTENCE_START_EXCLUSIONS:
        assert _name_candidate_key(entry) == entry, entry
    for entry in NAME_CANDIDATE_EXCLUSIONS:
        assert _name_candidate_key(entry) == entry, entry
    for entry in FIRST_PERSON_SPEAKER_EXCLUSIONS:
        assert _name_candidate_key(entry) == entry, entry


def test_the_narration_word_that_stole_three_lines_is_refused() -> None:
    """Ca thật: `Nghe gi\\u1ecdng c\\u1ee7a Victor b\\u00e2y gi\\u1edd…` sau `“L\\u00e0 t\\u00f4i, Victor.”`."""
    assert _leading_proper_name("Nghe gi\\u1ecdng c\\u1ee7a Victor b\\u00e2y gi\\u1edd c\\u00f3 v\\u1ebb \\u0111\\u00e3 nh\\u1eb9 h\\u01a1n.") is None
    assert _leading_proper_name("Tin nh\\u1eafn vi\\u1ebft nh\\u01b0 sau.") is None
    assert _leading_proper_name("Giai \\u0111i\\u1ec7u \\u1ea5y l\\u1eb7p l\\u1ea1i m\\u1ed9t l\\u1ea7n n\\u1eefa.") is None
    assert _leading_proper_name("Im l\\u1eb7ng m\\u1ed9t l\\u00fac l\\u00e2u.") is None


def test_a_real_name_opening_the_same_sentence_still_works() -> None:
    """Bộ canh chỉ được bớt tên bịa, không được bớt tên thật."""
    assert _leading_proper_name("Victor gi\\u1ea3i th\\u00edch th\\u00eam m\\u1ed9t l\\u1ea7n n\\u1eefa.") == "Victor"
    assert _leading_proper_name("Othello b\\u01b0\\u1edbc ra kh\\u1ecfi v\\u0103n ph\\u00f2ng.") == "Othello"


def test_the_model_may_not_name_a_first_person_pronoun_as_the_speaker() -> None:
    assert _speaker_that_is_not_a_pronoun("T\\u00f4i") == "UNKNOWN"
    assert _speaker_that_is_not_a_pronoun("M\\u00ecnh") == "UNKNOWN"
    assert _speaker_that_is_not_a_pronoun("M\\u00ccNH") == "UNKNOWN"
    assert _speaker_that_is_not_a_pronoun("ta") == "UNKNOWN"


def test_a_real_speaker_passes_through_untouched() -> None:
    assert _speaker_that_is_not_a_pronoun("Lucien") == "Lucien"
    assert _speaker_that_is_not_a_pronoun("NG\\u01af\\u1edcI TR\\u1ea2 L\\u1edcI") == "NG\\u01af\\u1edcI TR\\u1ea2 L\\u1edcI"
    assert _speaker_that_is_not_a_pronoun("BA T\\u01af\\u1edaC ELEIJAH") == "BA T\\u01af\\u1edaC ELEIJAH"
    assert _speaker_that_is_not_a_pronoun("Tim") == "Tim"
    assert _speaker_that_is_not_a_pronoun(None) == "UNKNOWN"


def test_a_third_person_honorific_is_left_alone() -> None:
    """`Anh`, `Em` là tên người Việt thường gặp; dự án có cơ chế khác cho nhãn chung chung."""
    for name in ("Anh", "Em", "C\\u00f4", "\\u00d4ng", "B\\u00e0"):
        assert _speaker_that_is_not_a_pronoun(name) == name, name
'''
t = root / "tests" / "test_a_pronoun_is_not_a_character.py"
io.open(t, "w", encoding="utf-8", newline="\n").write(TEST)
print(f"da tao {t}")
