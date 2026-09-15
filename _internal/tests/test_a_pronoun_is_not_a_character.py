"""Một đại từ hay một chữ mở đầu câu tường thuật không phải một nhân vật.

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
    assert _name_candidate_key("T\u00f4i") == "toi"
    assert _name_candidate_key("M\u00ecnh") == "minh"
    assert _name_candidate_key("B\u00c0") == "ba"
    assert _name_candidate_key("\u0110\u1ee8C") == "duc"
    assert _name_candidate_key("Lucien") == "lucien"


def test_both_exclusion_lists_are_written_folded() -> None:
    """Viết có dấu là viết một danh sách không bao giờ khớp - khoá đã bỏ dấu."""
    for entry in ATTRIBUTION_SENTENCE_START_EXCLUSIONS:
        assert _name_candidate_key(entry) == entry, entry
    for entry in NAME_CANDIDATE_EXCLUSIONS:
        assert _name_candidate_key(entry) == entry, entry


def test_the_narration_word_that_stole_three_lines_is_refused() -> None:
    """Ca thật: `Nghe gi\u1ecdng c\u1ee7a Victor…` ngay sau `“L\u00e0 t\u00f4i, Victor.”`."""
    assert _leading_proper_name("Nghe gi\u1ecdng c\u1ee7a Victor b\u00e2y gi\u1edd nh\u1eb9 h\u01a1n.") is None
    assert _leading_proper_name("Tin nh\u1eafn vi\u1ebft nh\u01b0 sau.") is None
    assert _leading_proper_name("Giai \u0111i\u1ec7u \u1ea5y l\u1eb7p l\u1ea1i m\u1ed9t l\u1ea7n n\u1eefa.") is None
    assert _leading_proper_name("Im l\u1eb7ng m\u1ed9t l\u00fac l\u00e2u.") is None


def test_a_real_name_opening_the_same_sentence_still_works() -> None:
    """Bộ canh chỉ được bớt tên bịa, không được bớt tên thật."""
    assert _leading_proper_name("Victor gi\u1ea3i th\u00edch th\u00eam m\u1ed9t l\u1ea7n n\u1eefa.") == "Victor"
    assert _leading_proper_name("Othello b\u01b0\u1edbc ra kh\u1ecfi v\u0103n ph\u00f2ng.") == "Othello"


def test_the_english_first_person_label_is_a_pronoun_too() -> None:
    """94 câu thoại của nhân vật chính cuốn 1 mang nhãn `ME`, và nó thành một nhân vật thật."""
    assert normalize_name("ME") in PRONOUNS
    assert normalize_name("Me") in PRONOUNS


def test_the_pronouns_that_were_already_right_stay_right() -> None:
    for name in ("T\u00f4i", "T\u00d4I", "M\u00ecnh", "ta", "H\u1eafn", "n\u00e0ng"):
        assert normalize_name(name) in PRONOUNS, name


def test_a_real_name_is_not_a_pronoun() -> None:
    for name in ("Lucien", "NG\u01af\u1edcI TR\u1ea2 L\u1edcI", "Tim", "Anh Tu\u1ea5n", "M\u1ecd"):
        assert normalize_name(name) not in PRONOUNS, name


def test_a_vietnamese_kinship_label_is_left_for_its_own_measurement() -> None:
    """`BÀ` là một người thật chưa được gọi tên; chỗ của nó là nhãn chung chung, không phải đây."""
    for name in ("B\u00c0", "\u00d4ng", "CHA", "M\u1eb8"):
        assert normalize_name(name) not in PRONOUNS, name
