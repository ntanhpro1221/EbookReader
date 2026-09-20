"""Phát lại CÂU TRẢ LỜI ĐÃ GHI của model qua luật host của cây hiện tại - đo bản vá host, không cần GPU.

    python scripts/model_eval/replay_from_candidates.py <project> [--chapters 426 429] [--gold throne...]
    python scripts/model_eval/replay_from_candidates.py <project> --chapters 426 --show 12

Mỗi lô phân tích đã chạy để lại `analysis_candidates.candidate_json`, trong đó `critic_rows[].candidate` là
**câu trả lời thô của model** (trước khi host sửa) và `segments[].data` là kết quả **sau** host. Script nạp lại
câu trả lời thô, chạy đúng `_validate` của cây đang có (tức cả chuỗi bản sửa host), rồi chấm theo đáp án chuẩn.

Vì thế nó trả lời được câu hỏi "bản vá host này thêm được bao nhiêu điểm trong SẢN XUẤT?" mà không phải chạy lại
LLM: chạy trong cây chưa vá và cây đã vá, so hai con số. Không gọi mạng, không dùng GPU, chỉ đọc project.

Đo lần đầu (20-09, lô 10 chương 426+429, 45 lô phân tích, 178 đoạn có đáp án): cây 8 bản vá của ranh giới 9 cho
điểm 79,4 - người nói 71,3% (bản ghi thật của project: 79,6 / 71,7%, lệch vì 2 đoạn thiếu, tức công cụ tái hiện
đúng); thêm 5 bản vá ghim cho ranh giới 10 thì **điểm 82,0 - người nói 77,0%**.

Ba giới hạn, đều cố ý:

  - chỉ chấm chương có đáp án chuẩn, và chỉ lô còn ứng viên trong sổ (`state='accepted'`);
  - GIỚI TÍNH đi thẳng từ bản đã ghi: host không quyết trường ấy (`resolve_gender` quyết, ở bước lập sổ nhân vật),
    nên đừng đọc cột ấy như một phép đo của bản vá host;
  - bản vá GOM TÊN (`ARTELI` -> `Artil`) chạy ở bước lập sổ nhân vật, KHÔNG ở `_validate`, nên nó không hiện trong
    con số này: điểm người nói đo cái NHÃN model viết ra, còn bản vá ấy sửa cái GIỌNG. Lợi thật của nó nằm ngoài
    thước đo này.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ebook_reader.analysis import _validate  # noqa: E402
from scripts.model_eval.score_models import (  # noqa: E402
    GOLD_DIR,
    GOLD_ROOT,
    load_gold,
    score_rows,
)


def replay(project: Path, chapters: set[str] | None) -> tuple[list[dict], dict[str, int]]:
    connection = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows_by_stable = {
        str(row["stable_id"]): dict(row)
        for row in connection.execute(
            "SELECT s.stable_id, s.seq, s.chapter_id, s.paragraph_index, s.kind_hint, s.kind, s.text, "
            "ch.title AS chapter FROM segments s JOIN chapters ch ON ch.id = s.chapter_id"
        )
    }
    out: list[dict] = []
    tally = {"lô": 0, "đoạn": 0, "bỏ vì lệch văn bản": 0, "bỏ vì thiếu đoạn": 0}
    for (raw,) in connection.execute(
        "SELECT candidate_json FROM analysis_candidates WHERE state='accepted' ORDER BY id"
    ):
        payload = json.loads(raw)
        critic_rows = payload.get("critic_rows") or []
        segments = payload.get("segments") or []
        if not critic_rows or len(critic_rows) != len(segments):
            tally["bỏ vì thiếu đoạn"] += 1
            continue
        group: list[dict] = []
        items: list[dict] = []
        genders: dict[str, str] = {}
        skip = False
        for critic, committed in zip(critic_rows, segments):
            stable_id = str(committed.get("stable_id") or "")
            row = rows_by_stable.get(stable_id)
            if row is None:
                skip = True
                break
            # Ghép theo VỊ TRÍ nên phải kiểm: văn bản của critic_row và của đoạn phải khớp.
            if " ".join(str(critic.get("text") or "").split()) != " ".join(str(row["text"]).split()):
                skip = True
                break
            group.append(row)
            items.append({"id": stable_id, **(critic.get("candidate") or {})})
            # Giới tính không nằm trong câu trả lời của model mà ở bản đã ghi: host không quyết trường ấy
            # (xem `resolve_gender`), nên cho nó đi thẳng qua để trục giới tính vẫn đọc được.
            genders[stable_id] = str((committed.get("data") or {}).get("gender") or "")
        if skip:
            tally["bỏ vì lệch văn bản"] += 1
            continue
        if chapters is not None and not any(str(row["chapter"]) in chapters for row in group):
            continue
        result = _validate(group, {"segments": items})
        tally["lô"] += 1
        for row in group:
            data = result.get(str(row["stable_id"]))
            if data is None:
                continue
            tally["đoạn"] += 1
            out.append({
                "chapter": row["chapter"],
                "seq": row["seq"],
                "kind": data["kind"],
                "speaker": data["speaker"],
                "gender": genders.get(str(row["stable_id"]), ""),
                "emotion": data["emotion"],
                "intensity": data["intensity"],
                "pace": data["pace"],
                "volume": data["volume"],
                "status": "",
                "text": row["text"],
            })
    connection.close()
    return out, tally


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", type=Path)
    parser.add_argument("--gold", default=GOLD_DIR.name, help="thư mục đáp án trong gold/ (mặc định cuốn 2)")
    parser.add_argument("--chapters", nargs="*", help="chỉ các chương này")
    parser.add_argument("--show", type=int, default=0, help="in N lỗi người nói đầu")
    args = parser.parse_args(argv)

    gold = load_gold(GOLD_ROOT / args.gold)
    wanted = set(args.chapters) if args.chapters else None
    if wanted:
        gold = {key: value for key, value in gold.items() if key[0] in wanted}
    rows, tally = replay(args.project, wanted)
    result = score_rows(gold, rows)
    print("  " + ", ".join(f"{name} {count}" for name, count in tally.items()))
    rates = result["rates"]
    print(f"  điểm {result['score']} | người nói {rates['speaker']} | cảm xúc {rates['emotion']} | "
          f"loại {rates['kind']} | g.tính {rates['gender']} | chấm {result['segments_scored']} đoạn, "
          f"thiếu {result['segments_missing']}")
    for miss in result["misses"]["speaker"][: args.show]:
        print(f"    - {miss}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
