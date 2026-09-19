"""Gom JSONL của gold_replay thành bộ train/dev/test cho LoRA, chia theo CHƯƠNG.

    python scripts/model_eval/build_training_set.py D:/Novels/Audiobooks/_model_eval_gold/audit_*/train_*.jsonl \
        --out D:/Novels/LLM_Train/data

Chia theo chương (không bao giờ trộn đoạn của một chương vào hai tập): chương trong `SPLIT["test"]` và
`SPLIT["dev"]` đi vào tập ấy, còn lại vào train. Tập test là đề thi so model - model tự huấn luyện KHÔNG được thấy nó;
bốn chương TMA trong test chính là bốn chương dùng so các model có sẵn (docs/LLM_EVAL.md). Mẻ vắt qua hai chương ở
hai tập khác nhau bị bỏ. Cùng một chương xuất hiện ở nhiều file (phát lại nhiều lần) thì chỉ giữ file mới nhất.

Mỗi dòng ra: {"messages": [system, user, assistant], "type", "gold", "chapters", "format"} - dạng chat của TRL; giữ
`format` (JSON schema của đúng lượt ấy) để chấm/giải mã có ràng buộc như sản xuất.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

# Sửa ở đây khi đáp án lớn thêm; KHÔNG đưa chương đã ở test sang train.
SPLIT: dict[str, dict[str, set[str]]] = {
    "test": {
        "throne_of_magical_arcana": {"351", "363", "378", "381"},
        "young_masters_pov": {"248"},
    },
    "dev": {
        "throne_of_magical_arcana": {"344"},
        "da_bao_la_cung_nhau_tu_sat": {"050"},
    },
}


def split_of(gold: str, chapters: list[str]) -> str | None:
    splits = set()
    for chapter in chapters:
        name = next((s for s, books in SPLIT.items() if chapter in books.get(gold, set())), "train")
        splits.add(name)
    return splits.pop() if len(splits) == 1 else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    # File mới nhất thắng cho mỗi (truyện, chương).
    newest: dict[tuple[str, str], Path] = {}
    records: dict[Path, list[dict]] = {}
    for path in sorted(args.inputs, key=lambda p: p.stat().st_mtime):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows = [row for row in rows if row.get("gold") and row.get("chapters")]
        records[path] = rows
        for row in rows:
            for chapter in row["chapters"]:
                newest[(row["gold"], chapter)] = path

    buckets: dict[str, list[dict]] = collections.defaultdict(list)
    dropped = collections.Counter()
    for path, rows in records.items():
        for row in rows:
            if any(newest[(row["gold"], chapter)] != path for chapter in row["chapters"]):
                dropped["cũ hơn"] += 1
                continue
            name = split_of(row["gold"], row["chapters"])
            if name is None:
                dropped["vắt hai tập"] += 1
                continue
            buckets[name].append({
                "messages": [
                    {"role": "system", "content": row["system"]},
                    {"role": "user", "content": row["prompt"]},
                    {"role": "assistant", "content": json.dumps(row["response"], ensure_ascii=False)},
                ],
                "type": row["type"], "gold": row["gold"], "chapters": row["chapters"], "format": row["format"],
            })

    args.out.mkdir(parents=True, exist_ok=True)
    for name in ("train", "dev", "test"):
        rows = buckets.get(name, [])
        (args.out / f"{name}.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
        )
        chapters = sorted({(row["gold"], c) for row in rows for c in row["chapters"]})
        kinds = collections.Counter(row["type"] for row in rows)
        print(f"{name:5}: {len(rows):5} mẫu ({dict(kinds)}), {len(chapters)} chương")
    missing = [(g, c) for s in ("test", "dev") for g, cs in SPLIT[s].items() for c in cs if (g, c) not in newest]
    if missing:
        print("THIẾU trong đầu vào:", missing)
    if dropped:
        print("bỏ:", dict(dropped))


if __name__ == "__main__":
    main()
