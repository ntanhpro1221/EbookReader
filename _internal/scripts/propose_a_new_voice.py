"""Đo preview của một giọng chưa dùng rồi SINH bản vá thêm nó vào `voice_catalog` - không tự sửa gì.

    runtime/.venv/Scripts/python.exe scripts/propose_a_new_voice.py --verify
    runtime/.venv/Scripts/python.exe scripts/propose_a_new_voice.py --report <audition.json> \
        --names "Mạnh Dũng,Adam bựa" [--previews <thư mục>] [--out <đường dẫn bản vá>]

`--verify` đo lại preview của các giọng ĐANG dùng và so với số đang ghi trong `voice_catalog`: nếu
cách đo này không tái lập được số cũ thì số mới không so được với số cũ, và mọi thứ sau đó là rác.
Chạy `--verify` trước, luôn. Chính nó đã bắt một lỗi thật ngày 18-09: `acoustics()` đo F3 bằng trung
vị trên khung hữu thanh, lệch tới 9,8% so với thang của catalog. Xem docstring của
`audition_presets.acoustics` cho lưới thiết lập đã dò và cách đúng ("Get mean" cả clip, trần theo giới).

## Vì sao có (18-09 02:3x)

Thêm một giọng vào kho không phải một dòng: `VIENEU_PRESETS`, `PRESET_VOCAL_TRACT_CM`,
`PRESET_PREVIEW_MEDIAN_PITCH_HZ`, `PRESET_MIN_PITCH_SEMITONES`, `VOICE_PREVIEW_FILENAMES`, cộng file
preview trong `ebook_reader/assets/voice_previews`. Sáu chỗ, và hai trong số đó là **số đo** phải lấy
từ đúng preview ấy bằng đúng cách đã dùng cho các giọng cũ (Praat, F0 trung vị và F3 → chiều dài ống
thanh `L = 5c / 4F3`). Chủ sách đang nghe 11 giọng và sẽ nhận một tập con; làm tay sáu chỗ cho từng
giọng giữa buổi sáng là cách chắc chắn để sai một chỗ.

`voice_catalog.py` bị khoá theo hash, nên script này KHÔNG sửa nó: nó in số đo, in cả những chỗ số mới
làm lệch giả định cũ (một giọng nam trầm hơn Phạm Tuyên thì dòng "đây là giọng nam trầm nhất" không
còn đúng), và ghi ra một bản vá trong `pending_patches/` để áp ở ranh giới.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ebook_reader.io_utils import slugify  # noqa: E402
from ebook_reader.voice_catalog import (  # noqa: E402
    PRESET_MIN_PITCH_SEMITONES,
    PRESET_PREVIEW_MEDIAN_PITCH_HZ,
    PRESET_VOCAL_TRACT_CM,
    VIENEU_PRESETS,
    VOCAL_TRACT_MAX_CM,
    VOCAL_TRACT_MIN_CM,
    VOICE_PREVIEW_FILENAMES,
)
from scripts.audition_presets import acoustics  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SHIPPED_PREVIEWS = ROOT / "ebook_reader" / "assets" / "voice_previews"
STAGED_PREVIEWS = ROOT / "scripts" / "pending_patches" / "assets" / "voice_previews"
# Hai ngưỡng khác nhau vì hai số tái lập khác nhau (đo 18-09 trên đúng 10 preview đang ship): ống
# thanh về đúng con số cũ (lệch 0,0% sau khi sửa cách đo F3 thành "Get mean" cả clip), còn F0 lệch
# trung bình 1,2% và lớn nhất 3,2% ở Thanh Bình - phần lệch còn lại là của chính clip/bản Praat và
# không đổi được thứ hạng trầm-bổng (3% chỉ là nửa cung), nên chấp nhận.
VERIFY_TRACT_TOLERANCE = 0.01
VERIFY_PITCH_TOLERANCE = 0.04
STYLE_CONSTANT = {"tu_nhien": "STYLE_NATURAL", "ke_chuyen": "STYLE_STORY", "doc_truyen": "STYLE_STORY",
                  "tin_tuc": "STYLE_NEWS"}
STYLE_WORD = {"STYLE_NATURAL": "Tự nhiên", "STYLE_STORY": "Kể chuyện", "STYLE_NEWS": "Tin tức"}
REGION_CONSTANT = {"Bắc": "REGION_NORTH", "Nam": "REGION_SOUTH", "Trung": "REGION_CENTRAL"}
GENDER_CONSTANT = {"male": "GENDER_MALE", "female": "GENDER_FEMALE"}


def semitones(higher: float, lower: float) -> float:
    from math import log2

    return 12.0 * log2(higher / lower)


def measure(name: str, gender: str, previews: Path) -> dict[str, float]:
    path = previews / f"{slugify(name)}.wav"
    if not path.exists():
        path = SHIPPED_PREVIEWS / f"{slugify(name)}.wav"
    if not path.exists():
        raise SystemExit(f"khong co preview cho {name}: {path}")
    numbers = acoustics([path], gender)
    return {"f0": round(numbers["f0_median_hz"], 1), "tract": round(numbers["vocal_tract_cm"], 1),
            "f3": numbers["f3_median_hz"], "preview": str(path)}


def verify(previews: Path) -> int:
    """Đo lại giọng đang dùng: cách đo này có ra đúng số trong catalog không?"""
    print("giong          F0 catalog  F0 do  lech    tract catalog  tract do  lech")
    worst = 0.0
    for preset in VIENEU_PRESETS:
        name = str(preset["name"])
        if name not in PRESET_PREVIEW_MEDIAN_PITCH_HZ or name not in PRESET_VOCAL_TRACT_CM:
            continue
        got = measure(name, str(preset["gender"]), previews)
        f0_old, tract_old = PRESET_PREVIEW_MEDIAN_PITCH_HZ[name], PRESET_VOCAL_TRACT_CM[name]
        f0_drift = abs(got["f0"] - f0_old) / f0_old
        tract_drift = abs(got["tract"] - tract_old) / tract_old
        worst = max(worst, f0_drift / VERIFY_PITCH_TOLERANCE, tract_drift / VERIFY_TRACT_TOLERANCE)
        print(f"{name:14} {f0_old:10.1f} {got['f0']:6.1f} {f0_drift:6.1%}    "
              f"{tract_old:12.1f} {got['tract']:9.1f} {tract_drift:6.1%}")
    print(f"\nnguong: ong thanh {VERIFY_TRACT_TOLERANCE:.0%}, F0 {VERIFY_PITCH_TOLERANCE:.0%}; "
          f"xa nguong nhat = {worst:.2f} lan nguong cua no")
    return 0 if worst <= 1.0 else 1


def min_pitch_proposal(name: str, gender: str, f0: float, measured: dict[str, dict]) -> tuple[int, str]:
    """Bậc hạ tối đa, theo đúng luật đọc ra được từ các số đang có.

    Nam: giọng trầm nhất là 0 (hạ nữa thì mất rõ tiếng), trong 3,5 nửa cung so với nó là -1, còn lại -2.
    Nữ: giọng trầm nhất là -1, còn lại -2. (Ngọc Linh cao hơn Ngọc Trân 2,1 nửa cung mà vẫn -2, nên
    bên nữ không có bậc trung gian.)
    """
    same = {n: hz for n, hz in PRESET_PREVIEW_MEDIAN_PITCH_HZ.items()
            if any(str(p["name"]) == n and str(p["gender"]) == gender for p in VIENEU_PRESETS)}
    same.update({n: m["f0"] for n, m in measured.items() if m["gender"] == gender})
    same[name] = f0
    floor_name = min(same, key=lambda n: same[n])
    if floor_name == name:
        return (0 if gender == "male" else -1), f"giong {gender} tram nhat ({f0:.1f} Hz)"
    gap = semitones(f0, same[floor_name])
    if gender == "male" and gap <= 3.5:
        return -1, f"cach giong tram nhat ({floor_name}, {same[floor_name]:.1f} Hz) {gap:.1f} nua cung"
    return -2, f"cach giong tram nhat ({floor_name}, {same[floor_name]:.1f} Hz) {gap:.1f} nua cung"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true", help="đo lại giọng đang dùng rồi so với catalog")
    parser.add_argument("--report", type=Path, help="JSON của audition_presets (lấy giới/vùng/phong cách)")
    parser.add_argument("--names", default="", help="các giọng chủ sách đã nhận, cách nhau bằng dấu phẩy")
    parser.add_argument("--previews", type=Path, default=STAGED_PREVIEWS)
    parser.add_argument("--out", type=Path, default=ROOT / "scripts" / "pending_patches" / "patch_the_pool_gains_voices.py")
    args = parser.parse_args()

    if args.verify:
        return verify(SHIPPED_PREVIEWS)
    names = [n.strip() for n in args.names.split(",") if n.strip()]
    if not names or args.report is None:
        parser.error("can --report va --names (hoac --verify)")
    report = json.loads(args.report.read_text(encoding="utf-8"))["presets"]

    measured: dict[str, dict] = {}
    for name in names:
        if name not in report:
            raise SystemExit(f"{name} khong co trong {args.report.name}")
        info = report[name]
        if str(info.get("verdict")) != "VAO POOL DUOC":
            print(f"  luu y: may cham {name} la {info.get('verdict')} - chu sach nhan thi van them")
        gender = str(info["gender"])
        got = measure(name, gender, args.previews)
        got.update({"gender": gender, "region": str(info["region"]), "style": str(info["style"])})
        measured[name] = got

    print(f"{'giong':15} {'gioi':7} {'vung':5} {'F0':>7} {'tract':>7}  bac ha  vi sao")
    rows = []
    for name, got in measured.items():
        step, why = min_pitch_proposal(name, got["gender"], got["f0"], {k: v for k, v in measured.items() if k != name})
        rows.append((name, got, step, why))
        print(f"{name:15} {got['gender']:7} {got['region']:5} {got['f0']:7.1f} {got['tract']:7.1f}  {step:^7} {why}")

    for name, got, _step, _why in rows:
        if not VOCAL_TRACT_MIN_CM <= got["tract"] <= VOCAL_TRACT_MAX_CM:
            print(f"  CHAN: {name} co ong thanh {got['tract']} cm, ngoai [{VOCAL_TRACT_MIN_CM}, {VOCAL_TRACT_MAX_CM}] "
                  "- cac bac formant cua no khong dung duoc")
        old_floor = min((n for n, p in ((str(p['name']), p) for p in VIENEU_PRESETS)
                         if str(p['gender']) == got["gender"] and n in PRESET_PREVIEW_MEDIAN_PITCH_HZ),
                        key=lambda n: PRESET_PREVIEW_MEDIAN_PITCH_HZ[n])
        if got["f0"] < PRESET_PREVIEW_MEDIAN_PITCH_HZ[old_floor]:
            print(f"  XEM LAI: {name} ({got['f0']:.1f} Hz) tram hon {old_floor} "
                  f"({PRESET_PREVIEW_MEDIAN_PITCH_HZ[old_floor]:.1f} Hz), ma PRESET_MIN_PITCH_SEMITONES dat "
                  f"{old_floor} = {PRESET_MIN_PITCH_SEMITONES.get(old_floor)} kem chu thich 'giong nam tram nhat'. "
                  "Ban va phai sua ca chu thich ay.")
        if name in VOICE_PREVIEW_FILENAMES:
            print(f"  CHAN: {name} da co trong catalog roi")

    args.out.write_text(render_patch(rows), encoding="utf-8")
    where = args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out
    print(f"\nda ghi ban va: {where}\n"
          "  doc lai (moi dong XEM LAI o tren phai tu sua tay trong ban va), thu tren ban sao,\n"
          "  roi xep vao pending_patches/apply_all.py ORDER o ranh gioi.")
    return 0


def render_patch(rows: list[tuple[str, dict, int, str]]) -> str:
    """Bản vá chèn sáu chỗ cho mỗi giọng, mỗi lần chèn có `assert` neo vào văn bản hiện có."""
    names = ", ".join(name for name, *_ in rows)
    presets = "".join(
        f'''    {{
        "name": "{name}", "gender": {GENDER_CONSTANT[got["gender"]]}, "region": {REGION_CONSTANT[got["region"]]},
        "style": {STYLE_CONSTANT[got["style"]]}, "description": "{"Nam" if got["gender"] == "male" else "Nữ"} · {got["region"]} · {STYLE_WORD[STYLE_CONSTANT[got["style"]]]}",
    }},
''' for name, got, _step, _why in rows)
    tract = "".join(f'    "{name}": {got["tract"]},\n' for name, got, _s, _w in rows)
    pitch = "".join(f'    "{name}": {got["f0"]},\n' for name, got, _s, _w in rows)
    steps = "".join(f'    "{name}": {step},  # {why}\n' for name, _got, step, why in rows)
    previews = "".join(f'    "{name}": "{slugify(name)}.wav",\n' for name, *_ in rows)
    copies = "".join(f'    "{slugify(name)}.wav",\n' for name, *_ in rows)
    measured_lines = "".join(f"#   {name:15} F0 {got['f0']:6.1f} Hz   ong thanh {got['tract']:5.1f} cm   "
                             f"bac ha {step:+d} ({why})\n" for name, got, step, why in rows)
    return f'''"""Vá voice_catalog.py: thêm giọng {names} vào kho giọng nhân vật.

Chạy: python patch_the_pool_gains_voices.py <root>

**XẾP Ở MỘT RANH GIỚI.** `voice_catalog.py` nằm trong `QUALITY_IMPLEMENTATION_FILES`, và thêm một
preset đổi cả `casting_presets` - tức đổi cách phân vai của mọi chương đúc lại sau đó.

Sinh bằng `scripts/propose_a_new_voice.py`. Số đo lấy từ chính preview của từng giọng, bằng đúng cách
đã dùng cho các giọng cũ (Praat: F0 trung vị, F3 → chiều dài ống thanh L = 5c/4F3):

{measured_lines}
Chủ sách đã nghe và nhận các giọng này trên trang chấm giọng 18-09.
"""
import io
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "voice_catalog.py"
s = io.open(p, encoding="utf-8").read()

INSERTS = (
    # (neo đứng TRƯỚC chỗ chèn, văn bản chèn)
    ("VIENEU_PRESETS: tuple[dict[str, str], ...] = (\\n", """{presets}"""),
    ("PRESET_VOCAL_TRACT_CM = {{\\n", """{tract}"""),
    ("PRESET_PREVIEW_MEDIAN_PITCH_HZ = {{\\n", """{pitch}"""),
    ("PRESET_MIN_PITCH_SEMITONES = {{\\n", """{steps}"""),
    ("VOICE_PREVIEW_FILENAMES = {{\\n", """{previews}"""),
)

for anchor, addition in INSERTS:
    assert anchor in s, f"khong tim thay neo: {{anchor!r}}"
    assert addition not in s, "da va roi"
    s = s.replace(anchor, anchor + addition, 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {{p}}")

# Preview đi cùng: kho giọng đọc file theo tên trong VOICE_PREVIEW_FILENAMES, thiếu file là hỏng.
staged = root / "scripts" / "pending_patches" / "assets" / "voice_previews"
shipped = root / "ebook_reader" / "assets" / "voice_previews"
for filename in (
{copies}):
    source = staged / filename
    assert source.exists(), f"thieu preview {{source}}"
    shutil.copy2(source, shipped / filename)
    print(f"da chep preview {{filename}}")
'''


if __name__ == "__main__":
    raise SystemExit(main())
