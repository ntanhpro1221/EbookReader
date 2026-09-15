"""Va character_registry.py + cli.py + scripts: mot cuon ke ngoi thu nhat phai biet "toi" LA AI.

Chay: python patch_a_first_person_book_knows_who_i_is.py <root>

**Phai ap SAU `patch_a_pronoun_is_not_a_character.py`** (cung nam trong `apply_all.ORDER`): ban va
ay them `me` vao `PRONOUNS`, va script nay assert rang no da vao cay truoc khi ghi.

## Cai gia da mat (do tren du lieu that, khong phong doan)

Cuon 1 ke o ngoi thu nhat. Mo hinh khai nguoi noi cho loi thoai cua chinh nhan vat chinh bang
**nhan dai tu**, ba cach viet, va do 04:00 ngay 2026-09-16 tren 118 project cuon 1:

    ME    94 cau      Toi   34 cau      TOI    1 cau      = 129 cau

Truoc hai ban va: `ME` co dong `characters` rieng, `importance='main'`, 54 lan nhac, va o lo 8 no
**chia giong voi JAKE**. Tren sach da ghep: `SAMAEL` 451 cau / 1 giong, `ME` 54 cau / **2 giong
nam khac**. Khong cong nao bat duoc: duoi mat moi phep kiem, `ME` la mot nhan vat va no nhat quan
trong tung chuong.

Sau `patch_a_pronoun_is_not_a_character`: nhung dong ay ve **nhom vo danh** - 2 giong sai thanh 1
giong sai nhung nhat quan. Dung huong, chua toi dich. Ban va nay la nua con lai.

## Vi sao la mot CONG TAC, khong phai mot luat

Hai cuon cho hai cau tra loi trai nhau:

    cuon 1 (ke ngoi thu nhat)  129 cau nhan ngoi thu nhat  -> TAT CA la loi nhan vat chinh
    cuon 2 (ke ngoi thu ba)     10 cau nhan `Minh`         -> CA 10 la NHAT KY cua nu phu thuy
                                                              ma Lucien dang doc (ch. 022/023/032)

Neu luat nay tu bat thi o cuon 2 no gan 10 cau nhat ky cho mot danh tinh sai - tuc bia ra mot
nguoi. Nen "toi la ai" la **mot su that ve cuon sach**: chu sach noi (`EBOOK_FIRST_PERSON`),
project GHI vao settings, va cuon nao khong noi thi khong doi mot chut nao.

Thuoc sang: `scripts/measure_the_first_person_labels.py` lay cum "doc ho" (nhat ky, ghi chep, ban
thao, la thu) quanh moi ca. Cuon 2 la **mau duong**: 9/10 ca sang. Cuon 1 sang dung **1** ca, va
doc tay thi ca ay la `"Sao the, Juli?"` cua chinh nguoi ke - sang chi vi chuoi `di thu` nam trong
chu `midi thuot tha`. Mot thuoc khong bat duoc mau duong thi ket luan "cuon 1 sach" vo gia tri.

## Ghi o dau, va vi sao khong o `DEFAULT_SETTINGS`

Khoa `voices.first_person_identity` **chi ton tai khi cuon sach noi ra no**. Neu de no trong
`DEFAULT_SETTINGS` voi gia tri rong thi `settings_hash` cua MOI project doi, va
`preview_project_creation` se coi moi project da co la "khac cau hinh" roi tao thu muc moi co hau
to hash - tuc mot luot `launch_batch.sh N` chay lai se THU LAI ca lo thay vi tiep tuc lo dang co.
Da do: `build_settings('high_quality')` khong co khoa nay cho ra dung hash cu.

Ghi vao settings chu khong doc `os.environ` trong goi: settings nam trong SQLite kem
`settings_hash`, nen mot lenh `run` o shell khac khong the im lang doi hanh vi cua project.

## Dai tu khong the la cau tra loi

`--first-person "Toi"` khong cuu duoc gi: phep so o `build_registry_and_cast` gap chu, nen nhan
`TOI` van khop `PRONOUNS` va van ve nhom vo danh. `cli create` tu choi thang; tang phan tich thi
noi ra roi khong lam gi - no khong duoc phep nem, vi nem giua luc phan tich la lam chet ca lo.

## Cach dung

    source scripts/book1.env   # da co export EBOOK_FIRST_PERSON="SAMAEL"
    bash scripts/launch_batch.sh 10 --range 261..278

Cuon 2 khong can lam gi. `FP_ARGS` la mot **mang** va duoc bung bang `${FP_ARGS[@]+...}`: mot
chuoi rong ghep vao dong lenh se thanh mot doi so rong, va `[ -n ... ] && arr=(...)` duoi `set -e`
cua `launch_batch.sh` se **thoat ca script** khi cuon khong khai bao gi (bat duoc luc thu tay).
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])


def edit(relative: str, pairs: list[tuple[str, str]]) -> None:
    """Thay tung cap, giu nguyen KIEU XUONG DONG cua file.

    `ebook_reader/cli.py` dung CRLF trong khi moi file khac dung LF, va mot ban va ghi de bang
    `newline="\\n"` se doi ca 1.565 dong cua no - mot diff khong ai doc duoc, cho mot thay doi
    ba dong. Doc bang `newline=""` de thay nguyen van, roi ghi lai dung kieu cu.
    """
    path = root / relative
    raw = io.open(path, encoding="utf-8", newline="").read()
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    for old, new in pairs:
        assert text.count(old) == 1, f"{relative}: khong khop {old.splitlines()[0][:60]!r}"
        text = text.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8", newline="").write(
        text.replace("\n", "\r\n") if crlf else text
    )
    print(f"da va {path}" + (" (giu CRLF)" if crlf else ""))


# ---------------------------------------------------------------- 1. character_registry.py
registry = io.open(root / "ebook_reader" / "character_registry.py", encoding="utf-8").read()
assert '"me", "tao", "tui", "tớ", "chúng tôi", "chúng mình",' in registry, (
    "phai ap patch_a_pronoun_is_not_a_character.py TRUOC ban va nay: `me` chua co trong PRONOUNS"
)

OLD_RESERVED = '''RESERVED_SPEAKERS = {"narrator": "NARRATOR", "unknown": "UNKNOWN"}'''
NEW_RESERVED = '''# Đại từ ngôi thứ nhất SỐ ÍT, tập con của `PRONOUNS`. Một cuốn kể ngôi thứ nhất có thể nói cho
# dự án biết "tôi" là ai (`voices.first_person_identity`), và khi ấy những nhãn này là lời của
# CHÍNH người ấy - xem `resolve_first_person_labels`.
#
# Số nhiều không ở đây: một câu mang nhãn `chúng ta` / `chúng tôi` / `bọn họ` không phải lời của
# một người, nên viết lại nó về một danh tính là sai. Ngôi thứ ba (`hắn`, `nàng`, `cô ấy`) càng
# không: đó là người khác, và chỗ của chúng vẫn là nhóm vô danh.
FIRST_PERSON_PRONOUNS = {"tôi", "ta", "mình", "tớ", "tao", "tui", "me"}
RESERVED_SPEAKERS = {"narrator": "NARRATOR", "unknown": "UNKNOWN"}'''

OLD_BUILD = '''def build_registry_and_cast(
    db: ProjectDB,
    settings: dict[str, Any],
    log: Callable[[str], None],
) -> None:'''
NEW_BUILD = '''def resolve_first_person_labels(
    db: ProjectDB,
    settings: dict[str, Any],
    log: Callable[[str], None],
) -> int:
    """Một cuốn kể ngôi thứ nhất: nhãn `tôi` / `ta` / `me` là lời của CHÍNH người kể.

    Không có `voices.first_person_identity` thì hàm này không làm gì - và đó là mặc định, vì
    "tôi là ai" là **một sự thật về cuốn sách**, không phải thứ máy suy ra được. Cùng họ với
    `EBOOK_SOURCE_DIR`, `EBOOK_PLAN`, `EBOOK_ALBUM`: chủ sách nói, dự án ghi vào project.

    Đo lúc 04:00 ngày 2026-09-16 trên dữ liệu thật của hai cuốn, và hai cuốn cho hai câu trả lời
    trái nhau - đó là lý do phải có công tắc thay vì một luật chung:

    - **Cuốn 1** (kể ngôi thứ nhất): 129 câu mang nhãn ngôi thứ nhất, ba cách viết (`ME` 94,
      `Tôi` 34, `TÔI` 1), tất cả là lời của nhân vật chính. Trước bản vá chúng bị cast thành
      **hai giọng nam khác** anh ta; sau `patch_a_pronoun_is_not_a_character` chúng về nhóm vô
      danh - một giọng sai nhưng nhất quán; với `first_person_identity=SAMAEL` chúng về đúng
      giọng mà 451 câu khác của anh ta đang dùng.
    - **Cuốn 2** (kể ngôi thứ ba): 10 câu mang nhãn `Mình`, và **cả 10 là nhật ký của nữ phù
      thủy** mà Lucien đang đọc (chương 022/023/032) - tức lời của người thứ ba, không phải của
      người kể. Nếu luật này tự bật thì nó sẽ gán nhật ký ấy cho một danh tính sai. Cuốn 2 để
      trống công tắc và không đổi một chút nào.

    Viết lại nhãn trong SQLite (`rewrite_speaker`) chứ không chỉ đổi lúc phân vai: sau đó mọi
    tầng dưới - báo cáo, `one_person_one_voice`, số lần nhắc, pin - đều thấy cùng một người, và
    đó chính là lối `RESERVED_SPEAKERS` ở trên đã đi cho `NARRATOR`/`UNKNOWN`.
    """
    identity = str(settings.get("voices", {}).get("first_person_identity", "")).strip()
    if not identity:
        return 0
    if normalize_name(identity) in PRONOUNS:
        # Một đại từ không thể là câu trả lời cho "tôi là ai": phép so ở `build_registry_and_cast`
        # gấp chữ, nên dù có viết lại nhãn thành `TÔI` thì nó vẫn khớp `PRONOUNS` và vẫn về nhóm
        # vô danh - công tắc sẽ im lặng vô dụng. `cli create --first-person` từ chối thẳng; ở đây
        # thì nói ra rồi không làm gì, vì nổ giữa lúc phân tích là làm chết cả lô.
        log(f'"{identity}" là một đại từ, không phải một danh tính - bỏ qua first_person_identity.')
        db.event(
            "warning",
            "FIRST_PERSON_IDENTITY_IS_A_PRONOUN",
            f"voices.first_person_identity={identity!r} is a pronoun, not a character",
            {"identity": identity},
        )
        return 0
    canonical = canonical_key(identity)
    moved = 0
    labels: list[str] = []
    for speaker in sorted({str(row["speaker"]) for row in db.list_segments()}):
        if normalize_name(speaker) not in FIRST_PERSON_PRONOUNS:
            continue
        if canonical_key(speaker) == canonical:
            continue
        rewritten = db.rewrite_speaker(speaker, canonical)
        if rewritten:
            moved += rewritten
            labels.append(f"{speaker}={rewritten}")
    if moved:
        log(
            f"{moved} câu mang nhãn đại từ ngôi thứ nhất về {canonical} "
            f"({', '.join(labels)}): cuốn này kể ở ngôi thứ nhất."
        )
        db.event(
            "info",
            "FIRST_PERSON_LABELS_RESOLVED",
            f"{moved} first-person pronoun lines were attributed to {canonical}",
            {"identity": canonical, "labels": labels},
        )
    return moved


def build_registry_and_cast(
    db: ProjectDB,
    settings: dict[str, Any],
    log: Callable[[str], None],
) -> None:'''

OLD_CALL = '''        if reserved and speaker != reserved:
            db.rewrite_speaker(speaker, reserved)

    _repair_cross_batch_dialogue_continuations(db, log)'''
NEW_CALL = '''        if reserved and speaker != reserved:
            db.rewrite_speaker(speaker, reserved)

    resolve_first_person_labels(db, settings, log)

    _repair_cross_batch_dialogue_continuations(db, log)'''

edit(
    "ebook_reader/character_registry.py",
    [(OLD_RESERVED, NEW_RESERVED), (OLD_BUILD, NEW_BUILD), (OLD_CALL, NEW_CALL)],
)

# ---------------------------------------------------------------- 2. cli.py (CRLF!)
OLD_IMPORT = '''from .character_registry import normalize_name'''
NEW_IMPORT = '''from .character_registry import PRONOUNS, normalize_name'''

OLD_ARG = '''    create.add_argument("--profile", choices=tuple(PROFILE_OVERRIDES), default="high_quality")
    create.add_argument("--settings-file", type=Path, help="Use a fully validated settings JSON instead")'''
NEW_ARG = '''    create.add_argument("--profile", choices=tuple(PROFILE_OVERRIDES), default="high_quality")
    create.add_argument(
        "--first-person",
        default="",
        help=(
            "Who 'I' is, for a book told in the first person: pronoun-labelled lines "
            "(tôi/ta/mình/me) are attributed to this character instead of an anonymous voice"
        ),
    )
    create.add_argument("--settings-file", type=Path, help="Use a fully validated settings JSON instead")'''

OLD_SETTINGS = '''def _settings_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.settings_file is not None:
        return load_settings(Path(args.settings_file).expanduser().resolve())
    return build_settings(str(args.profile))'''
NEW_SETTINGS = '''def _settings_from_args(args: argparse.Namespace) -> dict[str, Any]:
    first_person = str(getattr(args, "first_person", "") or "").strip()
    if args.settings_file is not None:
        if first_person:
            raise CliUsageError(
                "--first-person cannot be combined with --settings-file: put "
                "voices.first_person_identity in that file instead"
            )
        return load_settings(Path(args.settings_file).expanduser().resolve())
    if first_person and normalize_name(first_person) in PRONOUNS:
        raise CliUsageError(
            f"--first-person {first_person!r} is a pronoun, not a character: name whoever "
            '"I" is (for example --first-person SAMAEL)'
        )
    # Chỉ ghi khoá này khi cuốn sách NÓI RA nó. Nếu nó nằm trong `DEFAULT_SETTINGS` với giá trị
    # rỗng thì `settings_hash` của mọi project đổi, và `preview_project_creation` sẽ coi mọi
    # project đã có là "khác cấu hình" rồi tạo thư mục mới có hậu tố hash - tức một lượt
    # `launch_batch.sh N` chạy lại sẽ THU LẠI cả lô thay vì tiếp tục lô đang có.
    overrides = {"voices": {"first_person_identity": first_person}} if first_person else None
    return build_settings(str(args.profile), overrides)'''

edit("ebook_reader/cli.py", [(OLD_IMPORT, NEW_IMPORT), (OLD_ARG, NEW_ARG), (OLD_SETTINGS, NEW_SETTINGS)])

# ---------------------------------------------------------------- 3. scripts/book_paths.py
OLD_TABLE = '''    EBOOK_ALBUM             tên đĩa ghi vào thẻ ID3 của mọi chương                mặc định Throne of Magical Arcana
'''
NEW_TABLE = '''    EBOOK_ALBUM             tên đĩa ghi vào thẻ ID3 của mọi chương                mặc định Throne of Magical Arcana
    EBOOK_FIRST_PERSON      "tôi" trong cuốn này là ai (rỗng = kể ngôi thứ ba)   mặc định rỗng
'''

OLD_ALBUM = '''ALBUM = os.environ.get("EBOOK_ALBUM", "Throne of Magical Arcana")'''
NEW_ALBUM = '''ALBUM = os.environ.get("EBOOK_ALBUM", "Throne of Magical Arcana")
# "Tôi" trong cuốn này LÀ AI - rỗng nghĩa là cuốn kể ở ngôi thứ ba (cuốn 2), và khi rỗng thì
# không script nào truyền gì và hành vi không đổi một chút nào. Khi có, `launch_batch.sh` /
# `launch_repair.sh` truyền `--first-person` cho `cli create`, project GHI nó vào settings, và
# `character_registry.resolve_first_person_labels` gán những câu mang nhãn `tôi`/`ta`/`me` về
# đúng danh tính ấy thay vì về nhóm vô danh.
#
# Đo 04:00 ngày 2026-09-16: cuốn 1 có 129 câu như thế (ba cách viết) và tất cả là lời nhân vật
# chính; cuốn 2 có 10 câu và **cả 10 là nhật ký của một người thứ ba** - nên đây là công tắc của
# từng cuốn, không phải một luật chung.
FIRST_PERSON = os.environ.get("EBOOK_FIRST_PERSON", "")'''

OLD_DESCRIBE = '''        f" đĩa={ALBUM!r}"
    )'''
NEW_DESCRIBE = '''        f" đĩa={ALBUM!r}"
        + (f" tôi={FIRST_PERSON!r}" if FIRST_PERSON else "")
    )'''

edit(
    "scripts/book_paths.py",
    [(OLD_TABLE, NEW_TABLE), (OLD_ALBUM, NEW_ALBUM), (OLD_DESCRIBE, NEW_DESCRIBE)],
)

# ---------------------------------------------------------------- 4. scripts/book1.env
OLD_ENV = '''export EBOOK_ALBUM="Young Master's PoV: Woke Up As A Villain In A Game One Day"'''
NEW_ENV = '''export EBOOK_ALBUM="Young Master's PoV: Woke Up As A Villain In A Game One Day"
# "Toi" trong cuon 1 la SAMAEL: nguon noi thang ("Samael - tuc la toi -"), va do 04:00 ngay
# 2026-09-16: 129 cau mang nhan ngoi thu nhat (ME 94, Toi 34, TOI 1), tat ca la loi cua anh ta.
export EBOOK_FIRST_PERSON="SAMAEL"'''
edit("scripts/book1.env", [(OLD_ENV, NEW_ENV)])

# ---------------------------------------------------------------- 5. hai script phong lo
GUARD_ANCHOR = '''PLAN="${EBOOK_PLAN:-$ROOT/docs/PRODUCTION_PLAN_book2.md}"
'''
GUARD = GUARD_ANCHOR + '''
# "Toi" trong cuon nay la ai (EBOOK_FIRST_PERSON, xem scripts/book_paths.py). Rong = ke ngoi thu
# ba: khong truyen gi, `settings_hash` khong doi, va mot luot chay lai van MO LAI project cu thay
# vi tao project moi. Vi the la mot mang, khong phai mot chuoi rong ghep vao dong lenh.
FIRST_PERSON="${EBOOK_FIRST_PERSON:-}"
FP_ARGS=()
# `if` chu khong `[ ... ] && ...`: duoi `set -e` mot phep thu that bai o cuoi dong lam
# ca script thoat, nen dang `&&` se giet moi luot phong lo cua cuon KE NGOI THU BA.
if [ -n "$FIRST_PERSON" ]; then
  FP_ARGS=(--first-person "$FIRST_PERSON")
fi
'''

OLD_CREATE_BATCH = (
    '"$PY" -m ebook_reader.cli create \\\n'
    '  --output-root "$OUT" --source-dir "$SOURCE_DIR" \\\n'
    '  --range "$RANGE" --width 3 --title "$TITLE" --profile high_quality --json\n'
)
NEW_CREATE_BATCH = (
    '"$PY" -m ebook_reader.cli create \\\n'
    '  --output-root "$OUT" --source-dir "$SOURCE_DIR" \\\n'
    '  --range "$RANGE" --width 3 --title "$TITLE" --profile high_quality --json \\\n'
    '  ${FP_ARGS[@]+"${FP_ARGS[@]}"}\n'
)
edit("scripts/launch_batch.sh", [(GUARD_ANCHOR, GUARD), (OLD_CREATE_BATCH, NEW_CREATE_BATCH)])

OLD_CREATE_REPAIR = (
    '  PYTHONIOENCODING=utf-8 "$PY" -m ebook_reader.cli create \\\n'
    '    --output-root "$OUT" --source-dir "$SOURCE_DIR" \\\n'
    '    --range "$CH..$CH" --width 3 --title "$TITLE" --profile high_quality --json > /dev/null\n'
)
NEW_CREATE_REPAIR = (
    '  PYTHONIOENCODING=utf-8 "$PY" -m ebook_reader.cli create \\\n'
    '    --output-root "$OUT" --source-dir "$SOURCE_DIR" \\\n'
    '    --range "$CH..$CH" --width 3 --title "$TITLE" --profile high_quality --json \\\n'
    '    ${FP_ARGS[@]+"${FP_ARGS[@]}"} > /dev/null\n'
)
edit("scripts/launch_repair.sh", [(GUARD_ANCHOR, GUARD), (OLD_CREATE_REPAIR, NEW_CREATE_REPAIR)])

# ---------------------------------------------------------------- bai kiem
TEST = '''"""Một cuốn kể ngôi thứ nhất cần biết "tôi" LÀ AI — và một cuốn kể ngôi thứ ba thì không.

Đo lúc 04:00 ngày 2026-09-16 trên dữ liệu thật của cả hai cuốn, và hai cuốn cho hai câu trả lời
**trái nhau** — đó là lý do đây là một công tắc của từng cuốn, không phải một luật chung:

| cuốn | câu mang nhãn ngôi thứ nhất | là ai |
|---|---|---|
| 1 (kể ngôi thứ nhất) | 129 (`ME` 94, `Tôi` 34, `TÔI` 1) | nhân vật chính, cả 129 |
| 2 (kể ngôi thứ ba) | 10 (`Mình`) | **nhật ký của nữ phù thủy** Lucien đang đọc |

Cuốn 1 trước hai bản vá: 129 câu ấy cast thành **hai giọng nam khác** anh ta (`ME` có dòng
`characters` riêng, `importance='main'`, và ở lô 8 còn chia giọng với JAKE). Sau
`patch_a_pronoun_is_not_a_character`: về nhóm vô danh — một giọng sai nhưng nhất quán. Với
`voices.first_person_identity=SAMAEL`: về đúng giọng mà 451 câu khác của anh ta đang dùng.

Cuốn 2 thì luật này **phải im**: gán 10 câu nhật ký cho một danh tính nào đó là bịa ra một người.
Thước sàng (`scripts/measure_the_first_person_labels.py`) lấy cụm "đọc hộ" quanh mỗi ca: cuốn 2
sáng 9/10 ca (nhật ký, ghi chép, bản thảo), cuốn 1 sáng **1** ca duy nhất — và đọc tay thì ca ấy
là `"Sao thế, Juli?"` của chính người kể, sáng chỉ vì chữ `midi thướt tha` chứa chuỗi `di thư`.
"""
from __future__ import annotations

import inspect
from typing import Any

from ebook_reader.character_registry import (
    FIRST_PERSON_PRONOUNS,
    PRONOUNS,
    build_registry_and_cast,
    resolve_first_person_labels,
)


class _Db:
    def __init__(self, speakers: list[str]) -> None:
        self.rows = [{"speaker": speaker} for speaker in speakers]
        self.rewrites: list[tuple[str, str]] = []
        self.events: list[tuple[str, str, str, dict]] = []

    def list_segments(self) -> list[dict[str, Any]]:
        return list(self.rows)

    def rewrite_speaker(self, old_name: str, canonical_name: str) -> int:
        moved = [row for row in self.rows if row["speaker"] == old_name]
        for row in moved:
            row["speaker"] = canonical_name
        self.rewrites.append((old_name, canonical_name))
        return len(moved)

    def event(self, level: str, code: str, message: str, payload: dict) -> None:
        self.events.append((level, code, message, payload))


def _settings(identity: str | None) -> dict[str, Any]:
    voices: dict[str, Any] = {"narrator_voice": "Phạm Tuyên"}
    if identity is not None:
        voices["first_person_identity"] = identity
    return {"voices": voices}


def _log(_message: str) -> None:
    return None


def test_three_spellings_of_one_narrator_become_one_person() -> None:
    """Ca thật của cuốn 1: `ME`, `Tôi`, `TÔI` - một người, ba cách viết."""
    db = _Db(["ME", "ME", "Tôi", "TÔI", "SAMAEL", "JAKE", "NARRATOR"])

    moved = resolve_first_person_labels(db, _settings("SAMAEL"), _log)

    assert moved == 4
    assert [row["speaker"] for row in db.rows] == [
        "SAMAEL", "SAMAEL", "SAMAEL", "SAMAEL", "SAMAEL", "JAKE", "NARRATOR",
    ]
    assert db.events and db.events[0][1] == "FIRST_PERSON_LABELS_RESOLVED"
    assert db.events[0][3]["identity"] == "SAMAEL"


def test_a_third_person_book_is_left_completely_alone() -> None:
    """Cuốn 2: không có công tắc thì 10 câu nhật ký `Mình` không bị ai gán cho ai."""
    for settings in (_settings(None), _settings(""), _settings("   ")):
        db = _Db(["Mình", "Mình", "LUCIEN", "NARRATOR"])

        assert resolve_first_person_labels(db, settings, _log) == 0
        assert db.rewrites == []
        assert db.events == []
        assert [row["speaker"] for row in db.rows] == ["Mình", "Mình", "LUCIEN", "NARRATOR"]


def test_the_identity_is_written_the_way_every_other_name_is() -> None:
    """`canonical_key`: chủ sách gõ `Samael` thì nhãn vẫn về `SAMAEL` như mọi tên khác."""
    db = _Db(["tôi", "Samael"])

    resolve_first_person_labels(db, _settings("Samael"), _log)

    assert [row["speaker"] for row in db.rows] == ["SAMAEL", "Samael"]
    assert db.rewrites == [("tôi", "SAMAEL")]


def test_a_pronoun_is_not_an_answer_to_who_i_am() -> None:
    """`--first-person "Tôi"` không cứu được gì: phép so ở tầng dưới gấp chữ, nên nhãn `TÔI` vẫn
    khớp `PRONOUNS` và vẫn về nhóm vô danh. Công tắc sẽ im lặng vô dụng - nên nói ra.

    `cli create` từ chối thẳng (bài dưới). Ở tầng phân tích thì **không nổ**: một lệnh gõ sai
    không được phép làm chết cả lô giữa đường.
    """
    db = _Db(["Tôi", "Tôi"])

    assert resolve_first_person_labels(db, _settings("Tôi"), _log) == 0
    assert db.rewrites == []
    assert [event[1] for event in db.events] == ["FIRST_PERSON_IDENTITY_IS_A_PRONOUN"]
    assert [row["speaker"] for row in db.rows] == ["Tôi", "Tôi"]


def test_the_command_line_refuses_what_cannot_work() -> None:
    import argparse

    from ebook_reader.cli import CliUsageError, _settings_from_args

    def _args(**overrides: Any) -> argparse.Namespace:
        base: dict[str, Any] = {
            "settings_file": None,
            "profile": "high_quality",
            "first_person": "",
        }
        base.update(overrides)
        return argparse.Namespace(**base)

    assert "first_person_identity" not in _settings_from_args(_args())["voices"], (
        "khoá này chỉ được xuất hiện khi cuốn sách NÓI RA nó - xem docstring của "
        "`_settings_from_args`: một khoá mặc định đổi `settings_hash` của mọi project"
    )
    chosen = _settings_from_args(_args(first_person="  Samael  "))
    assert chosen["voices"]["first_person_identity"] == "Samael"

    for bad in (
        _args(first_person="Tôi"),
        _args(first_person="mình"),
        _args(first_person="SAMAEL", settings_file="settings.json"),
    ):
        try:
            _settings_from_args(bad)
        except CliUsageError:
            continue
        raise AssertionError(f"phải từ chối: {bad}")


def test_only_singular_first_person_labels_move() -> None:
    """`chúng ta` / `chúng tôi` / `bọn họ` là số nhiều: một câu của họ không phải lời một người."""
    plural = ["chúng ta", "chúng tôi", "chúng mình", "bọn họ"]
    third = ["hắn", "nàng", "cô ấy", "anh ấy", "ông ấy", "bà ấy", "người đó", "kẻ đó"]
    db = _Db([*plural, *third, "tôi"])

    moved = resolve_first_person_labels(db, _settings("SAMAEL"), _log)

    assert moved == 1
    assert db.rewrites == [("tôi", "SAMAEL")]
    assert [row["speaker"] for row in db.rows] == [*plural, *third, "SAMAEL"]


def test_every_first_person_label_is_already_a_pronoun() -> None:
    """Tập con của `PRONOUNS`: một nhãn không nằm trong đó thì hôm nay đã là một nhân vật thật.

    Nếu ai thêm một mục vào `FIRST_PERSON_PRONOUNS` mà quên `PRONOUNS` thì cuốn kể ngôi thứ ba
    sẽ vẫn cast nó như một người, và bài này đỏ trước khi chuyện đó tới sản xuất.
    """
    assert FIRST_PERSON_PRONOUNS <= PRONOUNS, FIRST_PERSON_PRONOUNS - PRONOUNS
    assert "me" in FIRST_PERSON_PRONOUNS, "nhãn tiếng Anh của cuốn 1 - 94 câu"
    assert not {"chúng ta", "chúng tôi", "chúng mình", "bọn họ"} & FIRST_PERSON_PRONOUNS


def test_the_labels_are_resolved_before_anything_reads_them() -> None:
    """Phải chạy TRƯỚC các phép sửa/gộp: chúng đối xử với dòng-tên-đại-từ theo luật riêng."""
    source = inspect.getsource(build_registry_and_cast)
    resolved = source.index("resolve_first_person_labels(db, settings, log)")

    for later in (
        "_repair_cross_batch_dialogue_continuations(db, log)",
        "_canonicalize_named_speakers(db, log)",
        "anonymous_by_gender",
    ):
        assert resolved < source.index(later), later
'''
t = root / "tests" / "test_a_first_person_book_knows_who_i_is.py"
t.write_text(TEST, encoding="utf-8", newline="\n")
print(f"da tao {t}")
