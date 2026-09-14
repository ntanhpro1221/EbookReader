"""Va character_registry.py: THIEU bang chung gioi tinh cung khong duoc giet lo, va gioi tinh NGUOI GHIM la bang chung.

Cuon 2 lo 2 chet 19:30:53 ngay 14-09, **sau 5 gio 30 phut phan tich tron 3.749 doan**:

    Casting input quality gate failed: named speakers missing gender={'LUKE': 4, 'NGHE': 3}

Hai cai ten, bay cau thoai, ca mot lo mat nhip. Chinh ham nay da thoi chan ca "gioi tinh MAU THUAN" tu
2026-09-09 (lo 1 chet sau 4 gio phan tich), voi ly le ghi day du trong
`test_gender_conflict_no_longer_fails_the_whole_book`:

    "Day la cong dat nhat trong du an: chuong hong thi mat mot chuong, cong nay hong thi mat ca cuon,
     ngay sau khi da tra xong phan dat nhat cua luot chay. Va no vi pham nguyen tac da chot o
     docs/SHIPPING_WITHOUT_A_LISTENER.md - mot phep kiem khong phan xu duoc thi khong duoc chan."

Ca "thieu" con nhe hon ca "mau thuan": mau thuan la model noi hai dieu, thieu la model khong noi gi.
Test cu khang dinh no PHAI nem (`test_recurring_named_speaker_without_gender_fails_before_voice_casting`)
**khong co mot dong ly le nao** - khac han test canh no. Ban va nay doi ca hanh vi va ca test ay.

**Lo thu hai, lo ra khi viet test:** cong khong doc `locked`, nen `cli cast --character X --gender male`
- chinh cach chua ma thong diep loi bao va ma `_command_cast` ton tai vi no - **khong** mo duoc cong.
Nguoi nghe tra loi dung cau hoi ay ma cong van chan. Gioi tinh do NGUOI ghim la bang chung manh nhat co
the co, nen no phai dem vao.

Hai cai ten cua ca that, de sau nay doc lai hieu vi sao:
  - `Luke`: nguoi that, 4 cau ("Vang thua ngai.", "Xin moi ngai.") - model khong doan duoc gioi tinh.
  - `Nghe`: **khong phai nguoi**. Nguon viet `"La toi, Victor." Nghe giong cua Victor bay gio...` va
    `"...Nam tuoc Othello." Nghe thay tieng on, Othello buoc ra...` - chu "Nghe" mo dau cau tuong thuat
    ngay sau loi thoai bi nhan thanh ten nguoi noi; ba cau ay thuc ra cua Victor va Othello. Viec chua
    cai do la viec KHAC (xem docs/OPTIMISATION_QUEUE.md), khong phai viec cua cong nay.

Sua:
  1. `missing_named_genders` di vao cung duong voi `gender_conflicts` - log to, tra ve cho cho goi phat
     `CASTING_GENDER_UNRESOLVED` - thay vi `raise`.
  2. Identity da co gioi tinh trong `locked` thi khong con la "thieu".
  3. `identity_instability` VAN nem: mot danh tinh mang hai voice profile la du lieu tu mau thuan, khong
     phai mot cau hoi khong tra loi duoc; di tiep la xuat ban hai giong cho mot nguoi.

Chay: python patch_no_gender_evidence_does_not_kill_the_book.py <root>
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "character_registry.py"
s = io.open(p, encoding="utf-8").read()

OLD_DETECT = '''        if (
            len(identity_rows) >= minimum_named_mentions
            and not gender_counts
            and not is_local_speaker(str(identity_rows[0]["speaker"]))
        ):
            missing_named_genders[identity] = len(identity_rows)
'''
NEW_DETECT = '''        if (
            len(identity_rows) >= minimum_named_mentions
            and not gender_counts
            and not is_local_speaker(str(identity_rows[0]["speaker"]))
            # Giới tính do NGƯỜI ghim (`cli cast --character X --gender ...`) là bằng chứng, và là
            # bằng chứng mạnh nhất có thể có. Không đọc nó thì chính cách chữa mà thông điệp lỗi
            # mách - và mà `_command_cast` tồn tại vì nó, "readable before casting has ever run" -
            # không mở được cổng: người nghe trả lời đúng câu hỏi ấy mà cổng vẫn chặn.
            and not str((locked or {}).get(identity, "")).strip()
        ):
            missing_named_genders[identity] = len(identity_rows)
'''
assert s.count(OLD_DETECT) == 1, "khong khop khoi phat hien missing_named_genders"
s = s.replace(OLD_DETECT, NEW_DETECT, 1)

OLD_RAISE = '''    issues: list[str] = []
    if missing_named_genders:
        issues.append(f"named speakers missing gender={missing_named_genders}")
    if identity_instability:
        issues.append(f"voice identity instability={identity_instability}")
    if issues:
        raise RuntimeError("Casting input quality gate failed: " + "; ".join(issues))
    return gender_conflicts
'''
NEW_RAISE = '''    # Thiếu bằng chứng giới tính cũng **không** giết lượt chạy nữa, vì đúng lý lẽ đã viết ở trên
    # cho ca mâu thuẫn - và ca này còn nhẹ hơn: mâu thuẫn là model nói hai điều, thiếu là model
    # không nói gì. Cuốn 2 lô 2 chết ở đây lúc 19:30 ngày 14-09 sau 5,5 giờ phân tích trọn 3.749
    # đoạn, vì hai cái tên bảy câu thoại: `Luke` (người thật, model không đoán được) và `Nghe`
    # (không phải người - chữ mở đầu câu tường thuật ngay sau lời thoại bị nhận thành tên).
    #
    # Đường ra vẫn như ca mâu thuẫn: đúc bằng giọng trung tính, log to, và trả về cho chỗ gọi
    # phát `CASTING_GENDER_UNRESOLVED` để nó nằm trong báo cáo. Người nghe sửa bằng một lệnh.
    for identity, mention_count in sorted(missing_named_genders.items()):
        detail = {
            "gender_evidence": "none",
            "mentions": int(mention_count),
            "cast_as": "unknown",
        }
        log(
            f"Giới tính của {identity} không có bằng chứng nào ({mention_count} câu); đúc bằng "
            f"giọng trung tính và đi tiếp. Sửa bằng: cli cast --character {identity} --gender ..."
        )
        gender_conflicts.setdefault(identity, detail)
    # Một danh tính mang hai voice profile thì VẪN ném: đó là dữ liệu tự mâu thuẫn, không phải
    # một câu hỏi không trả lời được, và đi tiếp là xuất bản hai giọng cho một người.
    if identity_instability:
        raise RuntimeError(
            "Casting input quality gate failed: voice identity instability="
            f"{identity_instability}"
        )
    return gender_conflicts
'''
assert s.count(OLD_RAISE) == 1, "khong khop khoi issues/raise"
s = s.replace(OLD_RAISE, NEW_RAISE, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

# Test cu khang dinh dung hanh vi vua bo. Doi no, va ghi ly le vao docstring - cai ma ban cu khong co.
t = root / "tests" / "test_character_casting.py"
s = io.open(t, encoding="utf-8").read()
OLD_TEST = '''def test_recurring_named_speaker_without_gender_fails_before_voice_casting(
    tmp_path: Path,
) -> None:
    db = _identity_db(tmp_path, [("Mag", "unknown")] * 3)

    with pytest.raises(RuntimeError, match="named speakers missing gender"):
        build_registry_and_cast(db, build_settings(), lambda _message: None)

    assert db.list_voice_profiles() == []
'''
NEW_TEST = '''def test_recurring_named_speaker_without_gender_no_longer_fails_the_whole_book(
    tmp_path: Path,
) -> None:
    """Cho tới 2026-09-14 chỗ này ném lỗi, và bản trước của bài này khẳng định nó phải ném.

    Bài ấy không có một dòng lý lẽ nào — khác hẳn `test_gender_conflict_no_longer_fails_the_whole_book`
    ngay bên trên, nơi lập luận được viết đủ. Và lập luận ấy áp vào đây còn mạnh hơn: **mâu thuẫn là
    model nói hai điều, thiếu là model không nói gì**. Nếu một câu hỏi không phán xử được thì không
    được chặn, thì một câu hỏi *không có dữ liệu nào để phán xử* càng không được chặn.

    Cái giá đã trả bằng tiền thật: cuốn 2 lô 2 chết 19:30 ngày 14-09 sau **5 giờ 30 phút** phân tích
    trọn 3.749 đoạn, vì `Luke` (4 câu) và `Nghe` (3 câu) — cái thứ hai còn không phải người.
    """
    said: list[str] = []
    db = _identity_db(tmp_path, [("Mag", "unknown")] * 3)

    build_registry_and_cast(db, build_settings(), said.append)

    assert db.list_voice_profiles(), "phải đúc giọng và đi tiếp, không dừng cả cuốn sách"
    assert any("MAG" in line and "cli cast" in line for line in said), "phải nói ra tên và cách sửa"
    codes = {str(row["code"]) for row in db.list_events()}
    assert "CASTING_GENDER_UNRESOLVED" in codes, "không im lặng: phải có sự kiện để vào báo cáo"


def test_a_listener_locked_gender_opens_the_gate(tmp_path: Path) -> None:
    """`cli cast` là cách chữa mà thông điệp lỗi mách; nó phải thật sự chữa được.

    Cổng cũ tính "thiếu giới tính" chỉ từ dữ liệu của model và không đọc `locked`, nên người nghe trả
    lời đúng câu hỏi được hỏi mà cổng vẫn chặn — và `_command_cast` tồn tại chính để trả lời **trước**
    khi cast chạy ("readable before casting has ever run").
    """
    said: list[str] = []
    db = _identity_db(tmp_path, [("Mag", "unknown")] * 3)
    db.lock_character_gender("Mag", "male")

    build_registry_and_cast(db, build_settings(), said.append)

    assert db.list_voice_profiles()
    assert not any("không có bằng chứng nào" in line for line in said), (
        "đã ghim thì không còn là 'thiếu bằng chứng'"
    )
'''
assert s.count(OLD_TEST) == 1, "khong khop test cu trong test_character_casting.py"
s = s.replace(OLD_TEST, NEW_TEST, 1)
io.open(t, "w", encoding="utf-8", newline="\n").write(s)
print(f"da doi test {t}")

TEST = '''"""No gender evidence must not kill a book: it is a weaker signal than a disagreement.

Book 2, batch 2 died at 19:30 on 2026-09-14 after 5.5 hours of analysis over all 3,749 segments,
because two names carried seven lines between them and the model offered no gender for either. The
same function had already stopped killing runs over a *disagreement*, for the reason written in its
own body: a check that cannot judge must not block, and this gate costs the whole book.

Two further facts this file pins down: a listener's locked gender counts as evidence (otherwise the
remedy the error message names cannot open the gate), and `identity_instability` still raises - one
identity holding two voice profiles is self-contradicting data, not an unanswerable question.
"""
from __future__ import annotations

import pytest

from ebook_reader.character_registry import _validate_casting_inputs


def _row(speaker: str, gender: str = "unknown", **extra):
    row = {
        "speaker": speaker,
        "gender": gender,
        "text": f"“{speaker} nói một câu.”",
        "chapter_id": 1,
        "canonical_character_id": None,
        "voice_profile_id": None,
    }
    row.update(extra)
    return row


def test_a_named_speaker_with_no_gender_evidence_is_reported_not_raised() -> None:
    said: list[str] = []
    rows = [_row("Luke") for _ in range(4)] + [_row("Lucien", "male") for _ in range(9)]

    unresolved = _validate_casting_inputs(rows, 3, said.append, {})

    assert "LUKE" in unresolved, unresolved
    assert unresolved["LUKE"]["gender_evidence"] == "none"
    assert unresolved["LUKE"]["mentions"] == 4
    assert any("cli cast --character LUKE" in line for line in said)
    assert "LUCIEN" not in unresolved


def test_a_speaker_the_model_did_gender_is_not_reported() -> None:
    rows = [_row("Victor", "male") for _ in range(5)]

    assert _validate_casting_inputs(rows, 3, lambda _m: None, {}) == {}


def test_one_identity_holding_two_voice_profiles_still_raises() -> None:
    rows = [
        _row("Victor", "male", canonical_character_id=1, voice_profile_id=1),
        _row("Victor", "male", canonical_character_id=1, voice_profile_id=2),
        _row("Victor", "male", canonical_character_id=1, voice_profile_id=2),
    ]

    with pytest.raises(RuntimeError, match="voice identity instability"):
        _validate_casting_inputs(rows, 3, lambda _m: None, {})


def test_a_locked_gender_is_evidence_and_is_not_reported() -> None:
    rows = [_row("Luke") for _ in range(4)]

    assert _validate_casting_inputs(rows, 3, lambda _m: None, {"LUKE": "male"}) == {}
'''
t = root / "tests" / "test_no_gender_evidence_does_not_kill_the_book.py"
io.open(t, "w", encoding="utf-8", newline="\n").write(TEST)
print(f"da tao {t}")
