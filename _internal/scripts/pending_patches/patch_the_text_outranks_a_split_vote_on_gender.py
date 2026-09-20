"""Vá character_registry.py: model CHIA PHIẾU về giới tính thì hỏi VĂN BẢN, đừng đếm phiếu.

Chạy: python patch_the_text_outranks_a_split_vote_on_gender.py <root>

## Vì sao (20-09, 09:3x)

`resolve_gender` hiện xếp hạng: phiếu model có ĐA SỐ là thắng ngay, văn bản chỉ được hỏi khi HOÀ. Nhưng chính
docstring của hàm viết: *"the text ... answers far better than the model does, because Vietnamese marks gender in
nearly every word it uses for a person."* Một đa số mỏng của model vẫn đủ để văn bản không bao giờ được hỏi - và đó
là chỗ sai:

| nhân vật | phiếu model | bằng chứng văn bản | luật cũ | thật |
|---|---|---|---|---|
| NEESHKA (lô 10) | 9 nam / 12 nữ | 23 nam / 7 nữ | **nữ** | nam: "Ngài Neeshka", "Ủy viên Neeshka, **ông** cảm thấy...", "Neeshka và những **quý ông** khác", và câu đối lập "**ngài** Neeshka, **cô** Milina" |
| CHLOE (lô 8) | 2 nam / 13 nữ | 26 nam / 5 nữ | **nữ** | nam: `docs/GOLD_GUIDE.md` đã ghi từ trước - chương 344 gọi "anh", "ngài Chloe" |
| LAUREN (lô 8) | 4 nam / 7 nữ | 11 nam / 0 nữ | **nữ** | nam: "Ý kiến của **ngài** Lauren", "**ông** không hề có ý chỉ trích Lauren" |

Giới tính sai là lỗi NGHE RÕ NHẤT: cả nhân vật đọc bằng giọng khác giới suốt cuốn sách.

Vá: khi phiếu model CHIA (cả hai giới đều có phiếu), hỏi văn bản TRƯỚC; văn bản dứt khoát thì văn bản thắng, không
dứt khoát thì mới đếm đa số như cũ. Model NHẤT TRÍ (chỉ một giới có phiếu) vẫn thắng - không đụng tới.

Ngưỡng "dứt khoát" có sẵn (>= 5 lần, tỉ lệ >= 3.0) chính là cái chặn đổi oan, và đo được: MILINA (lô 10) model nhất
trí nữ, văn bản 19 nam / 14 nữ (tỉ lệ 1,36 - không dứt khoát) -> không đổi, đúng ("cô Milina").

Đo trên 5 project (lô 6r, 7, 8, 9, 10 - 275 tên người nói): đổi ĐÚNG 3 ca trên, 0 ca đổi oan.

## Một cảnh báo về chính bằng chứng này (thêm 20-09 15:3x)

`_gendered_word_evidence` ĐẾM chữ chỉ người trong các segment có nêu tên nhân vật. Cùng chiều 20-09 tôi đã chứng
minh phép đếm ấy sai được: một phép đếm tương tự trên cửa sổ 45 ký tự quanh tên cho **17 ca rác trên 21**, trong đó
nó gọi "MỤ PHÙ THỦY GIÀ" là NAM - vì quanh một cái tên đầy chữ chỉ NGƯỜI KHÁC trong cảnh, mà nhân vật chính của
cuốn này là đàn ông và có mặt khắp nơi (xem `scripts/voice_matches_the_person.py`, mục ĐIỂM MÙ).

Bản vá này vẫn đứng, vì ba ca nó đổi đều kiểm được bằng tín hiệu MẠNH hơn - **danh xưng + tên**: "Ngài Neeshka" x6
và "quý ông", "ngài Chloe" (đã ghi trong `docs/GOLD_GUIDE.md` từ trước), "ngài Lauren" x15. Cộng thêm hai chốt sẵn
có: `_decisive` đòi >= 5 lần và tỉ lệ >= 3, và luật này chỉ chạy khi model CHIA PHIẾU.

Nhưng nếu về sau nó đổi sai một cái tên, đừng nới ngưỡng: **hỏi danh xưng trước**. `honorific_verdict` trong
`scripts/voice_matches_the_person.py` là bản đã đo của tín hiệu ấy (4 ca thật trên cuốn 2, không một ca rác).
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])


def patch(path: Path, old: str, new: str) -> None:
    source = io.open(path, encoding="utf-8").read()
    assert source.count(old) == 1, f"khong khop mot lan duy nhat trong {path.name}: {old.splitlines()[0]!r}"
    io.open(path, "w", encoding="utf-8").write(source.replace(old, new, 1))
    print(f"da va {path}")


patch(
    root / "ebook_reader" / "character_registry.py",
    '''    if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
        return ranked[0][0], "model_majority"
    names = {str(row["speaker"]) for row in identity_rows}
    evidence = _gendered_word_evidence(all_rows, names)
    decided = _decisive(evidence)
    if decided is not None:
        return decided, f"text:{evidence.get('male', 0)}nam/{evidence.get('female', 0)}nữ"
    return "unknown", "unresolved"''',
    '''    # Phiếu CHIA (cả hai giới đều có phiếu) nghĩa là model đang lưỡng lự, nên hỏi văn bản TRƯỚC khi đếm đa số:
    # một đa số mỏng vẫn thắng được thì văn bản không bao giờ được hỏi, và NEESHKA (9 nam/12 nữ trong khi văn bản
    # 23 nam/7 nữ, gọi "Ngài Neeshka", "quý ông"), CHLOE, LAUREN đều bị đọc bằng giọng nữ vì thế.
    names = {str(row["speaker"]) for row in identity_rows}
    evidence = _gendered_word_evidence(all_rows, names)
    decided = _decisive(evidence)
    if decided is not None:
        return decided, f"text:{evidence.get('male', 0)}nam/{evidence.get('female', 0)}nữ"
    if ranked and ranked[0][1] > ranked[1][1]:
        return ranked[0][0], "model_majority"
    return "unknown", "unresolved"''',
)

test = root / "tests" / "test_the_text_outranks_a_split_vote_on_gender.py"
test.write_text('''"""Model chia phiếu về giới tính thì văn bản quyết, model nhất trí thì model quyết."""
from __future__ import annotations

from ebook_reader.character_registry import resolve_gender


def row(speaker: str, gender: str, text: str = "") -> dict[str, str]:
    return {"speaker": speaker, "gender": gender, "text": text}


def test_a_split_vote_loses_to_decisive_text() -> None:
    ident = [row("NEESHKA", "female"), row("NEESHKA", "female"), row("NEESHKA", "male")]
    text = [row("NARRATOR", "unknown", "Ông Neeshka hỏi. Ông ấy nhìn quanh. Neeshka và những quý ông khác đáp lời ông. "
                                       "Lão Neeshka gật đầu, ông cụ mỉm cười.")]
    gender, why = resolve_gender(ident, [*ident, *text])
    assert gender == "male", why
    assert why.startswith("text:")


def test_a_unanimous_vote_keeps_its_answer() -> None:
    # MILINA: model nhất trí nữ, quanh tên toàn chữ chỉ nam vì cô ngồi giữa một hội đồng đàn ông.
    ident = [row("MILINA", "female") for _ in range(4)]
    text = [row("NARRATOR", "unknown", "Ngài Neeshka, ngài Evans và ông Levski quay sang cô Milina.")]
    gender, why = resolve_gender(ident, [*ident, *text])
    assert gender == "female", why
    assert why == "model"


def test_a_split_vote_with_no_evidence_falls_back_to_the_majority() -> None:
    ident = [row("X", "female"), row("X", "female"), row("X", "male")]
    gender, why = resolve_gender(ident, ident)
    assert (gender, why) == ("female", "model_majority")


def test_a_pinned_answer_still_outranks_everything() -> None:
    ident = [row("NEESHKA", "female")]
    text = [row("NARRATOR", "unknown", "Ông Neeshka, ông ấy, quý ông, ông, lão Neeshka, ông ta, cậu ta.")]
    assert resolve_gender(ident, [*ident, *text], {"NEESHKA": "female"}) == ("female", "listener")
''', encoding="utf-8")
print(f"da viet {test}")
