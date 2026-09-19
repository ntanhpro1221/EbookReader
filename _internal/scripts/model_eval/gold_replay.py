r"""Chạy khâu phân tích THẬT với một "Ollama giả" trả lời bằng đáp án chuẩn - để dựng dữ liệu huấn luyện.

    python scripts/model_eval/gold_replay.py <project> --gold young_masters_pov --out data/train/b1.jsonl

`<project>` là một project nháp đã chia đoạn (make_eval_project.py ... + analysis_only.py --segment-only), tạo
riêng cho việc này (model đặt tên gì cũng được, vd `gold:replay`). Mọi lượt `analyze_all` gọi Ollama đều bị chặn
ở `_stream_json_response`: câu hỏi của bộ sinh (generator) được trả lời bằng đáp án chuẩn của đúng các đoạn
ấy, câu hỏi của lượt phản biện (critic) được trả lời "đồng ý" với đề xuất. Nhờ vậy:

  - mỗi cặp (prompt ĐÚNG NHƯ SẢN XUẤT GỬI, câu trả lời đúng) ghi thành một dòng JSONL - dữ liệu để dạy model;
  - đáp án phải đi qua mọi luật kiểm của host (cảm xúc phải thuộc allowed_emotions, loại đoạn bị khoá, ...).
    Chỗ nào đáp án bị host bác thì in ra: đó là chỗ đáp án của tôi lệch luật của dự án và phải sửa;
  - chấm lại project này bằng score_models.py phải ra ~100%: phần thiếu là chỗ host tự sửa đè đáp án.

Chỉ chạy `analyze_all`; hai lượt hoà giải (danh tính NPC, cách đọc tên) chưa có đáp án nên bỏ qua.
Không gọi mạng, không cần GPU.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
for path in (ROOT, HERE):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from analysis_only import segment  # noqa: E402
from ebook_reader import analysis as A  # noqa: E402
from ebook_reader.database import ProjectDB  # noqa: E402
from ebook_reader.models import BookStatus, ProjectPaths  # noqa: E402
from ebook_reader.quality_policy import QUALITY_POLICY_VERSION, build_quality_policy, quality_policy_hash  # noqa: E402
from ebook_reader.worker import ProjectRunLock, _configure_logging, _load_locked_settings  # noqa: E402
from score_models import GOLD_ROOT, load_gold  # noqa: E402

FAKE_DIGEST = "sha256:" + "0" * 64
GENDER = {"m": "male", "f": "female"}


def _branch_for(schema: dict, batch_id: str) -> dict | None:
    """Nhánh `oneOf` của đúng ID (schema bị khoá theo từng ID khi host có ràng buộc)."""
    items = schema["properties"][next(k for k in ("segments", "verdicts") if k in schema["properties"])]["items"]
    for branch in items.get("oneOf", [items]):
        ids = branch["properties"]["id"].get("enum") or [branch["properties"]["id"].get("const")]
        if batch_id in ids or ids == [None]:
            return branch
    return None


class Replayer:
    def __init__(self, db: ProjectDB, gold: dict, out: Path | None) -> None:
        self.gold = gold
        self.out = out.open("w", encoding="utf-8") if out else None
        self.segments = [dict(row) for row in db.list_segments()]
        self.chapter_titles = {int(row["id"]): str(row["title"]) for row in db.list_chapters()}
        self.known_gender = {
            str(row["canonical_name"]).upper(): str(row["gender"]) for row in db.list_characters()
        }
        self.conflicts: list[str] = []
        self.counts = {"generator": 0, "critic": 0}

    # --- tra đáp án -----------------------------------------------------------------------
    def _locate(self, texts: list[str]) -> list[dict]:
        """Tìm dãy đoạn liên tiếp có đúng các text này (một mẻ luôn là các đoạn liền nhau)."""
        for start in range(len(self.segments) - len(texts) + 1):
            window = self.segments[start : start + len(texts)]
            if all(str(seg["text"]) == text for seg, text in zip(window, texts)):
                return window
        raise LookupError(f"không tìm thấy mẻ bắt đầu bằng {texts[0][:60]!r}")

    def _gold_for(self, segment: dict):
        return self.gold.get((self.chapter_titles[int(segment["chapter_id"])], int(segment["seq"])))

    # --- câu trả lời ------------------------------------------------------------------------
    def generator(self, request: dict) -> dict:
        rows = json.loads(request["prompt"].split("Các đoạn liên tiếp:\n", 1)[1].split("\n\nRàng buộc", 1)[0].split("\n\nKết quả lần trước", 1)[0])
        window = self._locate([row["text"] for row in rows])
        answer = []
        for row, segment in zip(rows, window):
            gold = self._gold_for(segment)
            branch = _branch_for(request["format"], row["id"])
            allowed_kinds = (branch or {}).get("properties", {}).get("kind", {}).get("enum") or sorted(A.ALLOWED_KINDS)
            allowed_emotions = (branch or {}).get("properties", {}).get("emotion", {}).get("enum") or row.get("allowed_emotions") or sorted(A.ALLOWED_EMOTIONS)
            if gold is None:  # tiêu đề chương: host khoá, trả mặc định
                answer.append({"id": row["id"], "kind": "narration", "speaker": "NARRATOR", "gender": "unknown",
                               "age": "unknown", "emotion": "neutral", "intensity": 0, "pace": "normal",
                               "volume": "normal", "confidence": 0.9})
                continue
            where = f"{gold.chapter}:{gold.seq}"
            kind = next((k for k in ("narration", "dialogue", "thought") if k in gold.kinds and k in allowed_kinds), None)
            if kind is None:
                kind = allowed_kinds[0]
                self.conflicts.append(f"{where} loại {sorted(gold.kinds)} bị khoá thành {allowed_kinds}")
            speaker = next(option for option, credit in gold.speakers if credit == 1.0)
            if kind == "narration":
                speaker = "NARRATOR"
            elif speaker == "NPC*":
                speaker = "NPC_LOCAL:người lạ"
            elif speaker == "NARRATOR" and kind != "narration" and len(gold.speakers) > 1:
                speaker = next((o for o, c in gold.speakers if c == 1.0 and o not in ("NARRATOR", "NPC*", "UNKNOWN")), "NARRATOR")
            emotion = next((e for e in gold.emotion_order if e in allowed_emotions), None)
            if emotion is None:
                emotion = allowed_emotions[0]
                self.conflicts.append(f"{where} cảm xúc {sorted(gold.emotions)} ngoài danh sách host {allowed_emotions}")
            low, high = gold.intensity
            intensity = low if emotion == "neutral" else min(high, max(low, 1))
            gender = GENDER.get(gold.gender) or self.known_gender.get(speaker.upper(), "unknown")
            if speaker in ("NARRATOR", "UNKNOWN") or gender not in ("male", "female"):
                gender = "unknown"
            answer.append({"id": row["id"], "kind": kind, "speaker": speaker, "gender": gender, "age": "unknown",
                           "emotion": emotion, "intensity": intensity, "pace": gold.pace_order[0],
                           "volume": gold.volume_order[0], "confidence": 0.9})
        return {"segments": answer, "pronunciations": []}

    def critic(self, request: dict) -> dict:
        prompt = request["prompt"]
        candidate_hash = re.match(r"candidate_hash=(\S+)", prompt).group(1)
        rows = json.loads(prompt[prompt.index("[", prompt.index("Hãy phản biện")):])
        floor = float(re.search(r"confidence_floor=([0-9]+(?:\.[0-9]+)?)", prompt).group(1))
        cap = float(re.search(r"confidence_cap=([0-9]+(?:\.[0-9]+)?)", prompt).group(1))
        verdicts = []
        for row in rows:
            branch = _branch_for(request["format"], row["id"]) or {}
            quote_rule = branch.get("properties", {}).get("evidence_quote", {})
            quote = (quote_rule.get("enum") or [quote_rule.get("const")] if ("enum" in quote_rule or "const" in quote_rule) else [str(row["text"])[: A.ANALYSIS_CRITIC_EVIDENCE_QUOTE_MAX_LENGTH]])[0]
            verdicts.append({"id": row["id"], **{f: row["candidate"][f] for f in A.DIRECTOR_DELIVERY_FIELDS},
                             "rationale": "Chức năng câu khớp với bằng chứng trong text.",
                             "evidence_quote": quote, "critic_confidence": round(min(cap, max(floor, 0.9)), 2)})
        return {"candidate_hash": candidate_hash, "verdicts": verdicts}

    def __call__(self, analyzer, request: dict, **_kw) -> dict:
        properties = request["format"].get("properties", {})
        if "segments" in properties:
            response, kind = self.generator(request), "generator"
        elif "verdicts" in properties:
            response, kind = self.critic(request), "critic"
        else:
            raise RuntimeError(f"gold_replay không trả lời loại câu hỏi này: {sorted(properties)}")
        self.counts[kind] += 1
        if self.out:
            self.out.write(json.dumps({"type": kind, "system": request["system"], "prompt": request["prompt"],
                                       "format": request["format"], "response": response}, ensure_ascii=False) + "\n")
        return response


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", type=Path)
    parser.add_argument("--gold", required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    paths = ProjectPaths.build(args.project.resolve())
    lock = ProjectRunLock(paths.root / ".worker.lock")
    lock.acquire()
    _configure_logging(paths.logs / "ebook_reader.log")
    db = ProjectDB(paths.db, synchronous="FULL")
    settings = _load_locked_settings(paths, db)
    policy = build_quality_policy(settings)
    policy_hash = quality_policy_hash(policy)
    db.set_current_quality_policy(policy_hash=policy_hash, policy_version=QUALITY_POLICY_VERSION, policy=policy)
    db.begin_run_generation()
    segment(db, settings, print)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
    replay = Replayer(db, load_gold(GOLD_ROOT / args.gold), args.out)

    def fake_available(self) -> bool:
        self._model_digest = FAKE_DIGEST
        return True

    A.OllamaBookAnalyzer.ensure_available = fake_available
    A.OllamaBookAnalyzer._current_model_digest = lambda self: FAKE_DIGEST
    A.OllamaBookAnalyzer._verify_locked_model_digest = lambda self, phase: None
    A.OllamaBookAnalyzer.release_model = lambda self: None
    A.OllamaBookAnalyzer._stop_managed_ollama = lambda self: None
    A.OllamaBookAnalyzer._stream_json_response = lambda self, request, **kw: replay(self, request, **kw)

    db.update_book(status=BookStatus.ANALYZING.value, stage="full_book_analysis")
    analyzer = A.OllamaBookAnalyzer(settings, db, lambda message: None, quality_policy_hash=policy_hash)
    analyzer.analyze_all(lambda: False, before_batch=lambda _index: None)
    if replay.out:
        replay.out.close()
    print(f"generator {replay.counts['generator']} lượt, critic {replay.counts['critic']} lượt")
    for conflict in replay.conflicts:
        print("  LỆCH LUẬT:", conflict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
