"""Va character_registry.py: hai nguoi CUNG GHIM mot giong khong duoc dung chung MOT CHUONG.

Ca that, lo 3 cuon 2, 14:23 ngay 15-09 — **5 va cham cung chuong, ca 5 deu la pin gap pin**:

    chuong 12  thanh_binh_f090  Verdi (5 cau) + Christopher (2 cau)     ca hai PIN vao giong nay
    chuong 14  thanh_binh_f090  Verdi (3) + Christopher (10)
    chuong 16  thai_son_f087    Rhine (6) + ORVARIT (1)
    chuong 32  thai_son_f108    SMILE (1) + SARD (6)
    chuong 36  thai_son_f093    Camil (2) + Nghe (1)

Chung do chinh thay doi 11:00 hom nay gay ra: `pin_the_book_cast` gio cho hai nguoi **chua tung cung
chuong** chia mot giong (dung luat holder cua bo cap giong), va o lo moi ho gap nhau. Cai gia da doi:
27 pin duoc ton trong, 4 nguoi giu duoc giong qua cac lo — nhung doanh nghia du an xep "hai nguoi mot
giong cung chuong" la khuyet tat NANG HON "mot nguoi doi giong giua cac chuong", nen dat nhu the la lo.

Va no con te hon the: buoc 4 ranh gioi duc lai nhung chuong ay, ma `launch_repair.sh` **cung** ghim
(cung thay doi 11:00) → project duc lai se ghim y nhu cu va **tai tao dung va cham** ay, dot ~12 phut
GPU moi chuong ma khong sua duoc gi. Dung hinh chuong 022 da lam hom 14-09.

Cho hong that nam o `_pinned_profile_id`: no ton trong pin **vo dieu kien**, khong he hoi "co ai khac
cung ghim giong nay va cung noi trong chuong nay khong". O thoi diem cast, phan tich da xong nen ban do
nguoi-noi-theo-chuong CO SAN — thieu chi la mot phep hoi.

Sua: truoc khi cast, bo pin cua nguoi **it cau hon** trong moi cap (giong, chuong) co hai nguoi ghim.
Nguoi bi bo pin di qua `allocator.choose()` — bo cap giong biet bac nao con trong va da ne nguoi cung
chuong (`_first_free_variant` → `shared_chapters`), nen ho nhan mot bac khac. Nguoi dong cau hon giu
nguyen giong da nghe. Log to, vi do la mot quyet dinh.

Lua chon "it cau hon" dung so cau TRONG CA LO, khong phai trong mot chuong: nguoi noi nhieu hon trong
lo la nguoi ma doi giong gay chu y nhieu hon.

Chay: python patch_two_pins_do_not_share_a_chapter.py <root>
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "character_registry.py"
s = io.open(p, encoding="utf-8").read()

OLD_HELPER = '''def _drop_pins_that_contradict_a_person(
'''
NEW_HELPER = '''def _drop_pins_that_share_a_chapter(
    rows: list[Any],
    locked_voices: dict[str, str],
    log: Any,
) -> dict[str, str]:
    """Bỏ pin của người ít câu hơn khi hai người CÙNG GHIM một giọng và CÙNG NÓI một chương.

    `_pinned_profile_id` tôn trọng pin vô điều kiện, và điều đó đúng cho tới khi pin được phép
    dùng chung: từ 11:00 ngày 2026-09-15 `pin_the_book_cast` cho hai người **chưa từng cùng
    chương** chia một giọng (đúng luật holder của bộ cấp giọng). Ở lô sau họ có thể gặp nhau, và
    lô 3 cuốn 2 gặp ngay: **5 va chạm cùng chương, cả 5 là pin gặp pin** — Verdi + Christopher ở
    chương 12 và 14, Rhine + ORVARIT ở 16, SMILE + SARD ở 32, Camil + Nghe ở 36.

    Doanh nghĩa của dự án xếp "hai người một giọng trong cùng chương" **nặng hơn** "một người đổi
    giọng giữa các chương" (người nghe tưởng là cùng một người, ngay trong một cảnh). Nên ở đúng
    chỗ hai điều ấy xung đột, nhất quán phải nhường.

    Ai giữ: người **nhiều câu hơn trong cả lô** - đổi giọng của họ gây chú ý hơn. Người kia mất
    pin và đi qua `allocator.choose()`, thứ đã tránh người cùng chương sẵn.
    """
    if not locked_voices:
        return locked_voices
    chapters: dict[str, set[int]] = {}
    lines: dict[str, int] = {}
    for row in rows:
        speaker = str(row["speaker"])
        if speaker.casefold() in RESERVED_SPEAKERS:
            continue
        identity = canonical_key(speaker)
        if identity not in locked_voices:
            continue
        chapters.setdefault(identity, set()).add(int(row["chapter_id"]))
        lines[identity] = lines.get(identity, 0) + 1
    by_voice: dict[str, list[str]] = {}
    for identity, voice in locked_voices.items():
        if identity in chapters:
            by_voice.setdefault(voice, []).append(identity)
    dropped: set[str] = set()
    for voice, identities in sorted(by_voice.items()):
        if len(identities) < 2:
            continue
        # Người nhiều câu trước; ai đã giữ thì người sau chỉ mất pin nếu CHẠM chương của họ.
        ranked = sorted(identities, key=lambda name: (-lines.get(name, 0), name))
        holders: list[str] = []
        for identity in ranked:
            clash = next(
                (
                    holder
                    for holder in holders
                    if chapters[identity] & chapters[holder]
                ),
                None,
            )
            if clash is None:
                holders.append(identity)
                continue
            dropped.add(identity)
            shared = sorted(chapters[identity] & chapters[clash])
            log(
                f"Bỏ giọng đã ghim của {identity} ({lines.get(identity, 0)} câu): trùng "
                f"{voice} với {clash} ({lines.get(clash, 0)} câu) ở chương {shared}. "
                "Hai người một giọng trong cùng chương nặng hơn một người đổi giọng."
            )
    if not dropped:
        return locked_voices
    return {name: voice for name, voice in locked_voices.items() if name not in dropped}


def _drop_pins_that_contradict_a_person(
'''
assert s.count(OLD_HELPER) == 1, "khong khop dau _drop_pins_that_contradict_a_person"
s = s.replace(OLD_HELPER, NEW_HELPER, 1)

OLD_CALL = '''    locked_voices = _drop_pins_that_contradict_a_person(
        db, locked_voices, locked_genders, locked_ages, log
    )
'''
NEW_CALL = '''    locked_voices = _drop_pins_that_contradict_a_person(
        db, locked_voices, locked_genders, locked_ages, log
    )
    # Sau khi pin đã qua phép kiểm "đúng phái", tới phép kiểm "không hai người một giọng trong
    # một chương". Thứ tự này có chủ ý: một pin sai phái thì bỏ dù có va chạm hay không, còn
    # phép kiểm dưới đây chỉ nói về những pin còn lại.
    locked_voices = _drop_pins_that_share_a_chapter(rows, locked_voices, log)
'''
assert s.count(OLD_CALL) == 1, "khong khop cho goi _drop_pins_that_contradict_a_person"
s = s.replace(OLD_CALL, NEW_CALL, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print(f"da va {p}")

TEST = '''"""Two pinned characters may not share a voice inside one chapter.

Batch 3 of book 2 produced five same-chapter collisions on 2026-09-15 and every one was pin
against pin: Verdi and Christopher both pinned to thanh_binh_f090 met in chapters 12 and 14,
Rhine and ORVARIT in 16, SMILE and SARD in 32, Camil and Nghe in 36. Shared pins arrived that
morning - pin_the_book_cast may now give one voice to two people who never met - and the new
batch is exactly where they meet.

The project ranks two people on one voice inside a chapter as the worse defect, so consistency
yields there: the pin of whoever speaks less in the batch is dropped and the allocator, which
already avoids same-chapter holders, gives them another variant.
"""
from __future__ import annotations

from ebook_reader.character_registry import _drop_pins_that_share_a_chapter

VOICE = "preset_thanh_binh_f090_p-04"
OTHER = "preset_thai_son_f100_p+00"


def _row(chapter: int, speaker: str):
    return {"chapter_id": chapter, "speaker": speaker}


def test_the_quieter_of_two_pins_in_one_chapter_loses_its_pin() -> None:
    said: list[str] = []
    rows = [_row(12, "Verdi")] * 5 + [_row(12, "Christopher")] * 2 + [_row(14, "Verdi")] * 3
    pins = {"VERDI": VOICE, "CHRISTOPHER": VOICE}

    kept = _drop_pins_that_share_a_chapter(rows, pins, said.append)

    assert kept == {"VERDI": VOICE}, kept
    assert any("CHRISTOPHER" in line and "chương [12]" in line for line in said), said


def test_two_pins_on_one_voice_that_never_meet_both_survive() -> None:
    rows = [_row(12, "Verdi")] * 5 + [_row(40, "Christopher")] * 9
    pins = {"VERDI": VOICE, "CHRISTOPHER": VOICE}

    kept = _drop_pins_that_share_a_chapter(rows, pins, lambda _m: None)

    assert kept == pins


def test_different_voices_in_one_chapter_are_untouched() -> None:
    rows = [_row(12, "Verdi")] * 5 + [_row(12, "Christopher")] * 9
    pins = {"VERDI": VOICE, "CHRISTOPHER": OTHER}

    assert _drop_pins_that_share_a_chapter(rows, pins, lambda _m: None) == pins


def test_a_silent_pinned_character_is_never_dropped() -> None:
    """Người im lặng trong lô này không va chạm với ai; pin của họ phải đi tiếp sang lô sau."""
    rows = [_row(12, "Verdi")] * 5
    pins = {"VERDI": VOICE, "CHRISTOPHER": VOICE}

    assert _drop_pins_that_share_a_chapter(rows, pins, lambda _m: None) == pins


def test_three_pins_on_one_voice_keep_the_two_who_do_not_meet() -> None:
    rows = (
        [_row(12, "Verdi")] * 10
        + [_row(12, "Christopher")] * 5
        + [_row(40, "Sard")] * 2
    )
    pins = {"VERDI": VOICE, "CHRISTOPHER": VOICE, "SARD": VOICE}

    kept = _drop_pins_that_share_a_chapter(rows, pins, lambda _m: None)

    assert kept == {"VERDI": VOICE, "SARD": VOICE}


def test_no_pins_is_a_no_op() -> None:
    assert _drop_pins_that_share_a_chapter([_row(1, "X")], {}, lambda _m: None) == {}
'''
t = root / "tests" / "test_two_pins_do_not_share_a_chapter.py"
io.open(t, "w", encoding="utf-8", newline="\n").write(TEST)
print(f"da tao {t}")
