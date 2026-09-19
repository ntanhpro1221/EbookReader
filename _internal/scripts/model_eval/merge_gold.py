"""So và hợp nhất hai bản gán nhãn làm mù của cùng một chương (quy trình trong docs/GOLD_GUIDE.md).

    python scripts/model_eval/merge_gold.py compare A.txt B.txt
    python scripts/model_eval/merge_gold.py merge A.txt B.txt --out gold/<truyện>/<chương>.txt \
        [--drop "THÁNH NỮ"] [--note "dòng ghi chú đầu file"]

`compare` in mọi câu lệch loại/người nói và độ đồng thuận (người nói ưu tiên, tập chấp nhận, loại, cảm xúc).
`merge` lấy HỢP các tập chấp nhận: lựa chọn ưu tiên theo A (người phân xử), tên đủ điểm ở một bên thì đủ điểm,
tên chỉ nửa điểm ở cả hai bên thì nửa điểm; `--drop` bỏ hẳn một nhãn (vd danh hiệu, quy tắc 11). Câu mà phân xử
kết luận khác hợp của hai bên thì sửa tay trong file kết quả và ghi vào ADJUDICATION.md.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from score_models import NARRATION_DEFAULT, Gold, parse_gold  # noqa: E402

LETTER = {"narration": "N", "dialogue": "D", "thought": "T"}
KIND_ORDER = ("narration", "dialogue", "thought")


def load(path: Path) -> dict[int, Gold]:
    # parse_gold lấy tên chương từ tên file; bản làm mù tên "claude_a_x.txt" nên chép sang tên trung tính.
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "chapter.txt"
        shutil.copyfile(path, copy)
        return {row.seq: row for row in parse_gold(copy)}


def written_kinds(path: Path) -> dict[int, list[str]]:
    """Thứ tự loại như A đã viết (parse_gold giữ loại dưới dạng tập): loại THẬT đứng trước (quy tắc 9)."""
    letters = {letter: kind for kind, letter in LETTER.items()}
    order = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        parts = raw.split()
        if len(parts) >= 2 and not raw.startswith("#") and parts[1] != "H":
            order[int(parts[0])] = [letters[letter] for letter in parts[1].split(",")]
    return order


def headings(path: Path) -> list[int]:
    seqs = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        parts = raw.split()
        if len(parts) == 2 and parts[1] == "H":
            seqs.append(int(parts[0]))
    return seqs


def preferred(row: Gold) -> str:
    return row.speakers[0][0]


def full(row: Gold) -> list[str]:
    return [name for name, credit in row.speakers if credit == 1.0]


def half(row: Gold) -> list[str]:
    return [name for name, credit in row.speakers if credit < 1.0]


def compare(a: dict[int, Gold], b: dict[int, Gold]) -> dict[str, float]:
    missing = sorted(set(a) ^ set(b))
    if missing:
        print(f"lệch dòng: {missing}")
    spoken = [s for s in sorted(set(a) & set(b)) if a[s].spoken or b[s].spoken]
    same_pref = compatible = 0
    for seq in sorted(set(a) & set(b)):
        x, y = a[seq], b[seq]
        if x.kinds != y.kinds or full(x) != full(y) or set(half(x)) != set(half(y)):
            print(f"  {seq:>4} A={','.join(sorted(LETTER[k] for k in x.kinds))} {','.join(full(x))}"
                  f"{' ~' + ','.join(half(x)) if half(x) else ''}"
                  f" | B={','.join(sorted(LETTER[k] for k in y.kinds))} {','.join(full(y))}"
                  f"{' ~' + ','.join(half(y)) if half(y) else ''}")
    for seq in spoken:
        x, y = a[seq], b[seq]
        same_pref += preferred(x) == preferred(y)
        compatible += preferred(x) in full(y) and preferred(y) in full(x)
    both = sorted(set(a) & set(b))
    kinds_same = sum(a[s].kinds == b[s].kinds for s in both)
    emo_pref = sum(a[s].emotion_order[:1] == b[s].emotion_order[:1] for s in both)
    emo_overlap = sum(bool(a[s].emotions & b[s].emotions) for s in both)
    n = max(len(spoken), 1)
    stats = {
        "spoken": len(spoken),
        "speaker_preferred": same_pref / n,
        "speaker_compatible": compatible / n,
        "kinds_same": kinds_same / max(len(both), 1),
        "emotion_preferred": emo_pref / max(len(both), 1),
        "emotion_overlap": emo_overlap / max(len(both), 1),
    }
    print(f"NGƯỜI NÓI {len(spoken)} câu: ưu tiên trùng {stats['speaker_preferred']:.1%}, "
          f"tương thích {stats['speaker_compatible']:.1%} | LOẠI trùng hệt {kinds_same}/{len(both)} | "
          f"CẢM XÚC ưu tiên {stats['emotion_preferred']:.1%}, giao {stats['emotion_overlap']:.1%}")
    return stats


def union(first: tuple[str, ...], second: tuple[str, ...]) -> list[str]:
    return list(first) + [item for item in second if item not in first]


def merge_row(x: Gold, y: Gold, drop: set[str], written: list[str] | None = None) -> str:
    first = written or list(KIND_ORDER)
    kinds = sorted(x.kinds | y.kinds, key=lambda k: (k not in x.kinds, first.index(k) if k in first else 9,
                                                     KIND_ORDER.index(k)))
    kind_field = ",".join(LETTER[k] for k in kinds)
    names_full = [n for n in union(tuple(full(x)), tuple(full(y))) if n not in drop]
    names_half = [n for n in union(tuple(half(x)), tuple(half(y))) if n not in drop and n not in names_full]
    speaker_field = ",".join(names_full + [n + "~" for n in names_half])
    emotions = union(x.emotion_order, y.emotion_order)
    low, high = min(x.intensity[0], y.intensity[0]), max(x.intensity[1], y.intensity[1])
    paces = union(x.pace_order, y.pace_order)
    volumes = union(x.volume_order, y.volume_order)
    gender = x.gender if x.gender != "u" else y.gender
    if names_full[:1] == ["NARRATOR"]:
        gender = "u"  # quy ước: giới tính theo nhân vật đứng đầu; NARRATOR đứng đầu thì u
    speaker0, emotions0, intensity0, paces0, volumes0, gender0 = NARRATION_DEFAULT
    if (kind_field == "N" and speaker_field == speaker0 and set(emotions) == set(emotions0)
            and (low, high) == tuple(intensity0) and set(paces) == set(paces0)
            and set(volumes) == set(volumes0) and gender == gender0):
        return f"{x.seq} N"
    return (f"{x.seq} {kind_field} {speaker_field} {','.join(emotions)} {low}-{high} "
            f"{','.join(paces)} {','.join(volumes)} {gender}")


def merge(path_a: Path, path_b: Path, out: Path, drop: set[str], notes: list[str]) -> None:
    a, b = load(path_a), load(path_b)
    if set(a) != set(b):
        raise SystemExit(f"hai bản lệch dòng: {sorted(set(a) ^ set(b))}")
    lines = [f"# {note}" for note in notes]
    rows = {seq: f"{seq} H" for seq in headings(path_a)}
    written = written_kinds(path_a)
    rows.update({seq: merge_row(a[seq], b[seq], drop, written.get(seq)) for seq in a})
    lines += [rows[seq] for seq in sorted(rows)]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{out}: {len(rows)} dòng")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    cmp_ = sub.add_parser("compare")
    cmp_.add_argument("a", type=Path)
    cmp_.add_argument("b", type=Path)
    mrg = sub.add_parser("merge")
    mrg.add_argument("a", type=Path)
    mrg.add_argument("b", type=Path)
    mrg.add_argument("--out", type=Path, required=True)
    mrg.add_argument("--drop", action="append", default=[], help="nhãn bỏ hẳn (so không phân biệt hoa thường)")
    mrg.add_argument("--note", action="append", default=[], help="một dòng ghi chú đầu file (lặp được)")
    args = parser.parse_args()
    if args.command == "compare":
        compare(load(args.a), load(args.b))
    else:
        merge(args.a, args.b, args.out, {name.upper() for name in args.drop}, args.note)


if __name__ == "__main__":
    main()
