"""Lỗi người nói mà MỌI model cùng sai - tức lỗi không phụ thuộc model, đúng loại host sửa được.

    python common_speaker_errors.py <root lượt đo>

Lý lẽ: một lỗi chỉ một model mắc là chuyện của model ấy; một lỗi mọi model cùng mắc là chỗ đề bài hoặc
luật host chưa đủ, và vá host thì MỌI model đều lợi. Bảy bản vá ranh giới 9-11 đã nâng người nói
69,0 -> 77,0% theo lối ấy, nhiều hơn mọi phép đổi model đo được tới nay.

In: các đoạn mà mọi model có dữ liệu đều KHÔNG được điểm nào ở trục người nói, gom theo hình dạng.
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

HERE = Path(r"D:/Novels/Ebook Reader/_internal/scripts/model_eval")
sys.path.insert(0, str(HERE))

from score_models import GOLD_ROOT, load_gold, read_project, speaker_credit  # noqa: E402

CHAPTERS = ("351", "363", "378", "381")


def shape(text: str, wanted: str, given: str) -> str:
    """Xếp một chỗ sai vào một hình dạng đọc được, để biết nên điều tra cái nào trước."""
    body = " ".join(text.split())
    opens_with_quote = bool(re.match(r'^[\s"“”\'‘’(\[]*[「『]?["“]', body)) or body[:1] in "“\"「『"
    if given.upper() in {"NARRATOR", ""}:
        return "model gán NGƯỜI KỂ cho câu của nhân vật" if opens_with_quote else "model gán NGƯỜI KỂ cho câu kể-nhưng-gold muốn nhân vật"
    if wanted.upper() == "NARRATOR":
        return "model gán NHÂN VẬT cho lời NGƯỜI KỂ"
    if given.upper().startswith(("NPC", "UNKNOWN")):
        return "model không nhận ra ai nói (NPC/UNKNOWN)"
    # Tên người khác trong cảnh: có xuất hiện trong chính câu ấy hay không?
    if re.search(re.escape(given.split(":")[-1]), body, flags=re.IGNORECASE):
        return "model lấy TÊN CÓ TRONG CÂU làm người nói"
    return "model lấy một người khác trong cảnh"


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else r"D:/Novels/Audiobooks/_model_eval_v2/21-09")
    gold = load_gold(GOLD_ROOT / "throne_of_magical_arcana")
    gold_chapters = {chapter for chapter, _ in gold}

    per_model: dict[str, dict[tuple[str, int], dict]] = {}
    for model_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        rows_by_key: dict[tuple[str, int], dict] = {}
        for chapter in CHAPTERS:
            project = next((model_dir / chapter).rglob("project.sqlite3"), None)
            if project is None:
                continue
            rows, _meta = read_project(project.parent, gold_chapters)
            for row in rows:
                rows_by_key[(str(row["chapter"]), int(row["seq"]))] = row
        if rows_by_key:
            per_model[model_dir.name] = rows_by_key
    if len(per_model) < 2:
        print("cần ít nhất hai model có dữ liệu")
        return 1
    print(f"{len(per_model)} model: {', '.join(per_model)}")

    shared = set.intersection(*(set(rows) for rows in per_model.values()))
    everyone_wrong: list[tuple[tuple[str, int], str, dict[str, str], dict]] = []
    only_some_wrong = 0
    scored = 0
    for key in sorted(shared):
        entry = gold.get((key[0], key[1]))
        if entry is None or not entry.speakers:
            continue
        scored += 1
        given = {name: str(rows[key]["speaker"] or "") for name, rows in per_model.items()}
        credits = {name: speaker_credit(entry, value) for name, value in given.items()}
        if all(credit <= 0.0 for credit in credits.values()):
            wanted = "/".join(option for option, _ in entry.speakers)
            everyone_wrong.append((key, wanted, given, per_model[next(iter(per_model))][key]))
        elif any(credit <= 0.0 for credit in credits.values()):
            only_some_wrong += 1

    print(f"\n{scored} đoạn có đáp án người nói và mọi model đều trả lời")
    print(f"   MỌI model cùng sai : {len(everyone_wrong)}  <- host sửa được, lợi cho mọi model")
    print(f"   chỉ một số sai     : {only_some_wrong}  <- chuyện của từng model")

    shapes: collections.Counter = collections.Counter()
    examples: dict[str, list[str]] = collections.defaultdict(list)
    for key, wanted, given, row in everyone_wrong:
        one = next(iter(given.values()))
        name = shape(str(row["text"] or ""), wanted.split("/")[0], one)
        shapes[name] += 1
        if len(examples[name]) < 3:
            body = " ".join(str(row["text"] or "").split())[:95]
            examples[name].append(f"{key[0]}:{key[1]} gold={wanted} | " +
                                  " ".join(f"{k.split('-')[0]}={v}" for k, v in given.items()) + f" | {body}")

    print("\nHình dạng các chỗ MỌI model cùng sai:")
    for name, count in shapes.most_common():
        print(f"\n  {count:>4}  {name}")
        for line in examples[name]:
            print(f"        {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
