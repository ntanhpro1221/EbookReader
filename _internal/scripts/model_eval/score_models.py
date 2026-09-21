r"""Chấm kết quả phân tích của từng model theo đáp án chuẩn trong `scripts/model_eval/gold/`.

    python scripts/model_eval/score_models.py                         # mọi project trong _model_eval
    python scripts/model_eval/score_models.py <project> [<project>...] # project chỉ định (vd lô 8 thật)
    python scripts/model_eval/score_models.py --json out.json          # ghi thêm bảng số ra file
    python scripts/model_eval/score_models.py --gold young_masters_pov <project>   # đáp án của truyện khác

Đáp án do Claude làm ngày 19-09 mà KHÔNG nhìn nhãn sản xuất (xem đầu mỗi file gold). Mỗi dòng gold nêu
tập đáp án chấp nhận được chứ không phải một đáp án duy nhất: cảm xúc và nhịp là chuyện cảm nhận, nên
chấm "có nằm trong tập hợp lý không" thay vì "có trùng đúng một nhãn không". Người nói thì khắt khe:
chỉ những lựa chọn liệt kê mới được điểm, hậu tố `~` là nửa điểm.

Điểm tổng (0..100) = 45% người nói + 15% cảm xúc + 10% loại đoạn + 10% cường độ + 5% nhịp + 5% âm lượng
+ 10% giới tính. Người nói nặng nhất vì đó là lỗi người nghe nhận ra ngay (sai giọng) và là phần duy nhất
có đúng sai khách quan. Tốc độ KHÔNG nằm trong điểm tổng; nó được in riêng để cân với chất lượng.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parents[1]) not in sys.path:
    sys.path.insert(0, str(HERE.parents[1]))

from ebook_reader.character_registry import PRONOUNS  # noqa: E402

# Một thư mục cho mỗi truyện: số chương của các truyện trùng nhau (cuốn 1 cũng có chương 351).
GOLD_ROOT = HERE / "gold"
GOLD_DIR = GOLD_ROOT / "throne_of_magical_arcana"
EVAL_ROOT = Path("D:/Novels/Audiobooks/_model_eval")

KIND_LETTERS = {"N": "narration", "D": "dialogue", "T": "thought"}
NARRATION_DEFAULT = ("NARRATOR", {"neutral"}, (0, 1), {"normal"}, {"normal"}, "u")
WEIGHTS = {
    "speaker": 45,
    "emotion": 15,
    "kind": 10,
    "intensity": 10,
    "pace": 5,
    "volume": 5,
    "gender": 10,
}


@dataclass(frozen=True)
class Gold:
    chapter: str
    seq: int
    kinds: frozenset[str]
    speakers: tuple[tuple[str, float], ...]
    emotions: frozenset[str]
    intensity: tuple[int, int]
    paces: frozenset[str]
    volumes: frozenset[str]
    gender: str
    # Thứ tự như đã viết: lựa chọn ĐẦU là cái ưu tiên (gold_replay dùng nó làm câu trả lời để dạy model).
    emotion_order: tuple[str, ...] = ()
    pace_order: tuple[str, ...] = ()
    volume_order: tuple[str, ...] = ()

    @property
    def spoken(self) -> bool:
        """Có người nói/nghĩ (không phải chỉ người kể) - phần chấm người nói."""
        return bool(self.kinds & {"dialogue", "thought"})


def speaker_key(name: str) -> str:
    """So tên không phân biệt hoa thường; mọi NPC_LOCAL gom về `NPC*` (nhãn cục bộ không so được).

    Một nhãn là ĐẠI TỪ ("MÌNH", "Tôi", "hắn") cũng gom về `NPC*`: ở bước phân vai
    `build_registry_and_cast` đẩy mọi tên thuộc `character_registry.PRONOUNS` vào nhóm VÔ DANH - tức
    người nghe nghe nó bằng đúng giọng của một NPC_LOCAL. Thiếu dòng này thì bộ chấm phạt nhãn mà model
    gõ ra thay vì chấm giọng người nghe nghe thấy: phép thử prompt 21-09 bị trừ oan 5 nhãn như thế
    (407:10-12 "MÌNH", đáp án nhận `NPC*`). Dùng chính tập của dây chuyền chứ không chép một danh sách
    thứ hai, để hai bên không bao giờ lệch nhau.
    """
    text = unicodedata.normalize("NFC", str(name or "")).strip()
    if text.upper().startswith("NPC_LOCAL") or text.upper() == "NPC*" or text.casefold() in PRONOUNS:
        return "NPC*"
    return re.sub(r"\s+", " ", text).upper()


def parse_gold(path: Path) -> list[Gold]:
    chapter = path.stem
    rows: list[Gold] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        seq, kind_field = int(parts[0]), parts[1]
        if kind_field == "H":
            continue
        if len(parts) == 2:
            if kind_field != "N":
                raise ValueError(f"{path.name}:{number}: dòng rút gọn chỉ dành cho N")
            speaker, emotions, intensity, paces, volumes, gender = NARRATION_DEFAULT
            speakers: tuple[tuple[str, float], ...] = ((speaker, 1.0),)
            emotion_order, pace_order, volume_order = ("neutral",), ("normal",), ("normal",)
        else:
            # Tên có dấu cách ("THẦN HƠI NƯỚC") nên tách từ PHẢI: 5 trường cuối cố định.
            if len(parts) < 8:
                raise ValueError(f"{path.name}:{number}: thiếu trường: {line!r}")
            speaker_field = " ".join(parts[2:-5])
            emotion_field, intensity_field, pace_field, volume_field, gender = parts[-5:]
            speakers = tuple(
                (speaker_key(option[:-1]), 0.5) if option.endswith("~") else (speaker_key(option), 1.0)
                for option in speaker_field.split(",")
            )
            emotion_order = tuple(emotion_field.split(","))
            pace_order = tuple(pace_field.split(","))
            volume_order = tuple(volume_field.split(","))
            emotions = set(emotion_order)
            low, _, high = intensity_field.partition("-")
            intensity = (int(low), int(high or low))
            paces = set(pace_field.split(","))
            volumes = set(volume_field.split(","))
        kinds = frozenset(KIND_LETTERS[letter] for letter in kind_field.split(","))
        rows.append(
            Gold(chapter, seq, kinds, speakers, frozenset(emotions), intensity,
                 frozenset(paces), frozenset(volumes), gender, emotion_order, pace_order, volume_order)
        )
    return rows


def load_gold(directory: Path = GOLD_DIR) -> dict[tuple[str, int], Gold]:
    gold: dict[tuple[str, int], Gold] = {}
    for path in sorted(directory.glob("*.txt")):
        for row in parse_gold(path):
            gold[(row.chapter, row.seq)] = row
    return gold


def speaker_credit(gold: Gold, speaker: str) -> float:
    key = speaker_key(speaker)
    return max((credit for option, credit in gold.speakers if option == key), default=0.0)


@dataclass
class Tally:
    earned: float = 0.0
    possible: int = 0
    misses: list[str] = field(default_factory=list)

    def add(self, credit: float, miss: str | None = None) -> None:
        self.earned += credit
        self.possible += 1
        if credit < 1.0 and miss is not None:
            self.misses.append(miss)

    @property
    def rate(self) -> float:
        return self.earned / self.possible if self.possible else 0.0


def dispute_row(where: str, axis: str, wanted: str, given: str, row: dict) -> dict:
    """Một chỗ thí sinh trả lời khác đáp án, kèm NGUYÊN VĂN đoạn - để phân xử bằng văn bản gốc."""
    chapter, _, seq = where.partition(":")
    return {
        "chương": chapter,
        "seq": int(seq),
        "trục": axis,
        "đáp án": wanted,
        "bài làm": given,
        "văn bản": " ".join(str(row["text"] or "").split()),
    }


def score_rows(gold: dict[tuple[str, int], Gold], rows: list[dict]) -> dict:
    tallies = {name: Tally() for name in WEIGHTS}
    disputes: list[dict] = []
    seen: set[tuple[str, int]] = set()
    unanalyzed = 0
    for row in rows:
        key = (str(row["chapter"]), int(row["seq"]))
        expected = gold.get(key)
        if expected is None:
            continue
        seen.add(key)
        if str(row.get("status", "")) == "pending":
            unanalyzed += 1
        where = f"{key[0]}:{key[1]}"
        kind = str(row["kind"] or "")
        speaker = str(row["speaker"] or "")
        tallies["kind"].add(1.0 if kind in expected.kinds else 0.0, f"{where} kind={kind}")
        if kind not in expected.kinds:
            disputes.append(dispute_row(where, "loại", "/".join(sorted(expected.kinds)), kind, row))
        if expected.spoken:
            credit = speaker_credit(expected, speaker)
            wanted = "/".join(option for option, _ in expected.speakers)
            tallies["speaker"].add(credit, f"{where} {speaker} (đúng: {wanted}) | {str(row['text'])[:60]}")
            if credit < 1.0:
                disputes.append(dispute_row(where, "người nói", wanted, speaker or "(trống)", row))
        elif speaker_key(speaker) != "NARRATOR":
            # Lời kể gán cho nhân vật: cũng là sai giọng, chấm chung vào người nói.
            tallies["speaker"].add(0.0, f"{where} lời kể gán cho {speaker} | {str(row['text'])[:60]}")
            disputes.append(dispute_row(where, "người nói", "NARRATOR", speaker, row))
        emotion = str(row["emotion"] or "")
        tallies["emotion"].add(1.0 if emotion in expected.emotions else 0.0,
                               f"{where} {emotion} (chấp nhận: {','.join(sorted(expected.emotions))})")
        intensity = int(row["intensity"] or 0)
        low, high = expected.intensity
        tallies["intensity"].add(1.0 if low <= intensity <= high else 0.0, f"{where} cường độ {intensity} ({low}-{high})")
        tallies["pace"].add(1.0 if str(row["pace"] or "") in expected.paces else 0.0, f"{where} nhịp {row['pace']}")
        tallies["volume"].add(1.0 if str(row["volume"] or "") in expected.volumes else 0.0, f"{where} âm lượng {row['volume']}")
        if expected.gender in {"m", "f"} and speaker_credit(expected, speaker) > 0 and speaker_key(speaker) != "NPC*":
            gender = str(row.get("gender") or "")
            wanted_gender = {"m": "male", "f": "female"}[expected.gender]
            tallies["gender"].add(1.0 if gender == wanted_gender else 0.0, f"{where} {speaker} giới tính {gender}")
    missing = len(set(gold) - seen)
    total = sum(WEIGHTS[name] * tallies[name].rate for name in WEIGHTS)
    return {
        "segments_scored": len(seen),
        "segments_missing": missing,
        "unanalyzed": unanalyzed,
        "score": round(total, 1),
        "rates": {name: round(100 * tally.rate, 1) for name, tally in tallies.items()},
        "counts": {name: [round(tally.earned, 1), tally.possible] for name, tally in tallies.items()},
        "misses": {name: tally.misses for name, tally in tallies.items()},
        "disputes": disputes,
    }


def read_project(project: Path, chapters: set[str]) -> tuple[list[dict], dict]:
    connection = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT ch.title AS chapter, s.seq, s.kind, s.speaker, s.gender, s.age, s.emotion,
                       s.intensity, s.pace, s.volume, s.confidence, s.status, s.text
                FROM segments s JOIN chapters ch ON ch.id = s.chapter_id
                ORDER BY ch.chapter_index, s.seq
                """
            )
            if str(row["chapter"]) in chapters
        ]
        book = connection.execute("SELECT settings_json, analysis_model_name FROM book").fetchone()
        model = str(book["analysis_model_name"] or json.loads(book["settings_json"])["analysis"]["model"])
        pronunciations = []
        try:
            pronunciations = [
                (str(r[0]), str(r[1]))
                for r in connection.execute("SELECT surface, spoken_form FROM pronunciations ORDER BY surface")
            ]
        except sqlite3.Error:
            pass
    finally:
        connection.close()
    run_file = project / "model_eval_run.json"
    run = json.loads(run_file.read_text(encoding="utf-8")) if run_file.is_file() else {}
    return rows, {"model": model, "run": run, "pronunciations": pronunciations}


def eval_projects(root: Path = EVAL_ROOT) -> list[Path]:
    return sorted(path.parent for path in root.glob("*/*/project.sqlite3"))


DISPUTE_COLUMNS = ("thí sinh", "chương", "seq", "trục", "đáp án", "bài làm", "phán xử", "bằng chứng", "văn bản")


def write_disputes(results: list[dict], path: Path) -> None:
    """Phiếu phân xử làm MÙ: thí sinh thành TS1..TSn theo băm tên, nên thứ tự không nói gì về điểm.

    Phân xử phải dựa vào cột `văn bản` (và chương gốc), không dựa vào "model nào nói". Cột `phán xử`
    điền TS_SAI / ĐÁP_ÁN_SAI / NHẬP_NHẰNG, cột `bằng chứng` dán câu trong truyện đã quyết định.
    """
    order = sorted(results, key=lambda item: hashlib.sha1(str(item["model"]).encode("utf-8")).hexdigest())
    labels = {id(item): f"TS{index}" for index, item in enumerate(order, start=1)}
    rows = [
        {"thí sinh": labels[id(item)], "phán xử": "", "bằng chứng": "", **dispute}
        for item in results
        for dispute in item["disputes"]
    ]
    rows.sort(key=lambda row: (row["chương"], row["seq"], row["trục"], row["thí sinh"]))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DISPUTE_COLUMNS, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    key = "\n".join(f"{labels[id(item)]}\t{item['model']}\t{item['project']}" for item in order)
    path.with_suffix(path.suffix + ".key").write_text(key + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("projects", nargs="*", type=Path)
    parser.add_argument("--gold", default=GOLD_DIR.name, help="thư mục đáp án trong gold/ (mặc định cuốn 2)")
    parser.add_argument("--json", type=Path, help="ghi toàn bộ kết quả (kể cả danh sách lỗi) ra file")
    parser.add_argument("--misses", type=int, default=0, help="in N lỗi người nói đầu tiên của mỗi model")
    parser.add_argument(
        "--chapters",
        nargs="*",
        help="chỉ chấm các chương này (tên chương như trong project) - để chấm một lô đang bay, "
        "khi các chương sau chưa phân tích",
    )
    parser.add_argument(
        "--dispute-out",
        type=Path,
        help="ghi phiếu phân xử (TSV) mọi chỗ bài làm khác đáp án, tên model ĐÃ GIẤU thành TS1..TSn; "
        "khoá giải giấu ghi ra <file>.key - chỉ mở SAU khi đã phân xử xong (xem docs/GOLD_GUIDE.md)",
    )
    args = parser.parse_args(argv)

    gold = load_gold(GOLD_ROOT / args.gold)
    if args.chapters:
        wanted = set(args.chapters)
        gold = {key: value for key, value in gold.items() if key[0] in wanted}
        if not gold:
            raise SystemExit(f"không có đáp án cho chương {sorted(wanted)} trong gold/{args.gold}")
    chapters = {chapter for chapter, _ in gold}
    projects = args.projects or eval_projects()
    results = []
    for project in projects:
        rows, meta = read_project(project, chapters)
        result = score_rows(gold, rows)
        result.update({"project": str(project), **meta})
        results.append(result)

    results.sort(key=lambda item: -item["score"])
    header = f"{'model':22} {'điểm':>5} {'người nói':>9} {'cảm xúc':>7} {'loại':>5} {'c.độ':>5} {'nhịp':>5} {'âm l.':>5} {'g.tính':>6} {'giây':>7}"
    print(header)
    for item in results:
        rates = item["rates"]
        seconds = item["run"].get("total_seconds", "")
        print(
            f"{item['model'][:22]:22} {item['score']:5.1f} {rates['speaker']:9.1f} {rates['emotion']:7.1f} "
            f"{rates['kind']:5.1f} {rates['intensity']:5.1f} {rates['pace']:5.1f} {rates['volume']:5.1f} "
            f"{rates['gender']:6.1f} {seconds!s:>7}"
        )
        if item["segments_missing"] or item["unanalyzed"]:
            print(f"    thiếu {item['segments_missing']} đoạn, chưa phân tích {item['unanalyzed']}")
        for miss in item["misses"]["speaker"][: args.misses]:
            print(f"    - {miss}")
    if args.json:
        args.json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.dispute_out:
        write_disputes(results, args.dispute_out)
        print(f"phiếu phân xử: {args.dispute_out} ({sum(len(r['disputes']) for r in results)} chỗ), "
              f"khoá giấu tên: {args.dispute_out}.key")
    return 0


if __name__ == "__main__":
    sys.exit(main())
