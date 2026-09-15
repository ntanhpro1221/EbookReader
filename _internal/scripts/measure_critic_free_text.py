"""Hai truong tu do cua phan bien nang bao nhieu: `rationale` va `evidence_quote`."""
import json
import sqlite3
import statistics
import sys
from pathlib import Path

p = Path(r"D:/Novels/Audiobooks/book2/_versions/v0.3.0-lo04/lo04_f81716f380/project.sqlite3")
c = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
c.row_factory = sqlite3.Row
rows = c.execute(
    "SELECT evidence_json, outcome_json FROM analysis_critic_attempts WHERE evidence_json IS NOT NULL"
).fetchall()
c.close()


def walk(node, quotes, rationales):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "evidence_quote" and isinstance(value, str):
                quotes.append(value)
            elif key == "rationale" and isinstance(value, str):
                rationales.append(value)
            else:
                walk(value, quotes, rationales)
    elif isinstance(node, list):
        for item in node:
            walk(item, quotes, rationales)
    elif isinstance(node, str) and node.startswith("{"):
        try:
            walk(json.loads(node), quotes, rationales)
        except Exception:
            pass


quotes: list[str] = []
rationales: list[str] = []
for row in rows:
    for column in ("evidence_json", "outcome_json"):
        try:
            walk(json.loads(row[column] or "null"), quotes, rationales)
        except Exception:
            continue


def report(name, items):
    if not items:
        print(f"{name:<16} khong thay trong evidence_json/outcome_json")
        return 0.0
    lengths = [len(x) for x in items]
    mean = statistics.fmean(lengths)
    print(
        f"{name:<16} {len(items):>5} gia tri | ky tu trung vi {statistics.median(lengths):>4.0f}"
        f" / tb {mean:>5.1f} / max {max(lengths):>4} | ~{mean/3:>5.1f} token"
    )
    return mean


print(f"{len(rows)} luot phan bien co evidence_json")
quote_mean = report("evidence_quote", quotes)
rationale_mean = report("rationale", rationales)
if quote_mean and rationale_mean:
    per_segment = (quote_mean + rationale_mean) / 3
    print()
    print(f"hai truong ~{per_segment:.0f} token moi doan; batch trung binh 4,4 doan"
          f" => ~{per_segment * 4.4:.0f} token moi lan goi")
    print("do duoc: phan bien sinh 582 token/lan, de xuat 246 => chenh 336")
sys.exit(0)
