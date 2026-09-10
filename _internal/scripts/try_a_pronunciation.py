"""Cách đọc nào của một cái tên được giọng đọc phát ra ỔN ĐỊNH nhất? — đo, không đoán.

    python scripts/try_a_pronunciation.py Jake Giếch Giếc Giết "Giây-cơ" Jake --takes 10
    python scripts/try_a_pronunciation.py Jake --report      # chỉ đọc lại kết quả đã chạy

**Chỉ chạy khi GPU rảnh** (giữa hai lô). Nó sinh audio thật, nên chạy song song với một lô là
lấy GPU của lô ấy.

Vì sao cần: `Jake → Giếch` có **1.827 lần neo qua cả ba lô, 0% khớp ở cả ba, 89 cách đọc khác
nhau**, và cùng một câu ra `Giật` rồi `Dịch` — hai âm khác nhau. Bạn thân của nhân vật chính
được gọi bằng một cái tên khác nhau gần như mỗi lần. Xem docs/A_NAME_READ_MANY_WAYS.md.

Nhưng "dạng đọc nào tốt hơn" là một câu hỏi về **âm thanh**, và tôi không có tai. Cái tôi có là
Whisper: nếu mười bản thu của cùng một câu được phiên thành cùng một chuỗi thì giọng đọc ổn định;
nếu ra mười chuỗi thì không. Đó là `đỉnh%` trong `scripts/name_is_read_the_same_way.py`, và
script này tạo dữ liệu để tính nó cho những dạng đọc **chưa từng dùng**.

Cách làm, cố ý dùng lại đường ống thật thay vì dựng harness riêng: mỗi ứng viên một project một
chương, cùng một câu lặp `--takes` lần (mỗi lần một seed khác vì `stable_id` khác), cách đọc ứng
viên ghim vào bảng `pronunciations`, rồi `run` như mọi lô khác. Bản thu đi qua đúng những cổng
mà một chương thật đi qua, nên kết quả nói về sản phẩm chứ không về một phòng thí nghiệm.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "runtime" / ".venv" / "Scripts" / "python.exe"
LAB = Path("D:/Novels/Audiobooks/_pronunciation_lab")
# Một câu trung tính, đủ dài để qua ngưỡng kiểm nhịp (24 ký tự đọc) và có tên ở giữa câu chứ
# không ở cuối: một cái tên ở cuối câu bị trộn với khoảng lặng kết đoạn, và đó là biến số khác.
SENTENCE = "Tôi gọi {name} rồi bước ra khỏi phòng."


def _say(line: str) -> None:
    try:
        print(line)
    except (UnicodeEncodeError, OSError, ValueError):
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower() or "x"


def build_project(surface: str, spoken: str, takes: int, index: int) -> Path | None:
    """Một project một chương: câu lặp `takes` lần, cách đọc ứng viên đã ghim."""
    folder = LAB / f"{slug(surface)}_{index:02d}_{slug(spoken)}"
    source = folder / "Text"
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
    source.mkdir(parents=True)
    lines = [SENTENCE.format(name=surface) for _ in range(takes)]
    (source / "000.txt").write_text(
        f"Chương 0 - Thử cách đọc\n\n" + "\n\n".join(lines) + "\n",
        encoding="utf-8",
    )
    created = subprocess.run(
        [
            str(PYTHON), "-m", "ebook_reader.cli", "create",
            "--output-root", str(folder / "out"),
            "--source-dir", str(source),
            "--range", "000..000", "--width", "3",
            "--title", f"pron_{slug(spoken)}",
            "--profile", "high_quality", "--json",
        ],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if created.returncode != 0:
        _say(f"  create thất bại cho {spoken!r}: {(created.stderr or '')[:200]}")
        return None
    projects = sorted((folder / "out").glob("pron_*"))
    if not projects:
        _say(f"  không thấy project cho {spoken!r}")
        return None
    project = projects[-1]
    sys.path.insert(0, str(ROOT))
    from ebook_reader.character_registry import canonical_key  # noqa: PLC0415
    from ebook_reader.database import ProjectDB  # noqa: PLC0415

    ProjectDB(project / "project.sqlite3").upsert_pronunciation(
        surface=surface,
        normalized_surface=canonical_key(surface).lower(),
        spoken_form=spoken,
        confidence=0.98,
        source="pronunciation_experiment",
        locked=True,
    )
    return project


def run_project(project: Path) -> None:
    subprocess.run(
        [str(PYTHON), "-m", "ebook_reader.cli", "run", str(project), "--json"],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    while True:
        try:
            conn = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
            try:
                beats = [
                    time.time() - float(row[0] or 0.0)
                    for row in conn.execute("SELECT heartbeat_at FROM worker_leases")
                ]
                left = sum(
                    1
                    for (status,) in conn.execute("SELECT status FROM chapters")
                    if status in {"pending", "analyzing", "synthesizing", "verifying"}
                )
            finally:
                conn.close()
        except sqlite3.Error:
            time.sleep(20)
            continue
        if not left and not (beats and min(beats) < 180.0):
            return
        time.sleep(20)


def heard_forms(project: Path, surface: str) -> collections.Counter[str]:
    """Whisper viết gì ở chỗ cái tên, đếm theo dạng. Đọc từ neo tên trong `quality_checks`."""
    forms: collections.Counter[str] = collections.Counter()
    try:
        conn = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
    except sqlite3.Error:
        return forms
    try:
        rows = conn.execute(
            "SELECT metrics_json FROM quality_checks"
            " WHERE failure_codes_json LIKE '%LOCKED_NAME_ANCHOR%'"
        ).fetchall()
    except sqlite3.Error:
        return forms
    finally:
        conn.close()
    for (payload,) in rows:
        try:
            anchors = json.loads(payload)["locked_name_anchor_metrics"]["anchors"]
        except (ValueError, KeyError, TypeError):
            continue
        for anchor in anchors:
            if str(anchor.get("surface")) != surface:
                continue
            if anchor.get("matched"):
                forms["(khớp cổng)"] += 1
                continue
            form = " ".join(str(t) for t in (anchor.get("aligned_tokens") or [])).strip()
            forms[form or "(bỏ hẳn)"] += 1
    return forms


def report(surface: str) -> int:
    folders = sorted(LAB.glob(f"{slug(surface)}_*"))
    if not folders:
        _say(f"chưa có lượt thử nào cho {surface!r} trong {LAB}")
        return 1
    _say(f"{'cách đọc':20s} {'bản thu':>8s} {'dạng':>5s} {'đỉnh%':>6s}  Whisper hay viết")
    _say("-" * 92)
    ranked: list[tuple[float, str, int, int, str]] = []
    for folder in folders:
        projects = sorted((folder / "out").glob("pron_*")) if (folder / "out").is_dir() else []
        if not projects:
            continue
        spoken = folder.name.split("_", 2)[-1]
        forms = heard_forms(projects[-1], surface)
        total = sum(forms.values())
        if not total:
            continue
        top = forms.most_common(3)
        peak = top[0][1] / total * 100
        ranked.append((peak, spoken, total, len(forms), ", ".join(f"{f!r}×{n}" for f, n in top)))
    for peak, spoken, total, kinds, top in sorted(ranked, reverse=True):
        _say(f"{spoken[:19]:20s} {total:8d} {kinds:5d} {peak:5.0f}%  {top}")
    _say("")
    _say("đỉnh% cao = giọng đọc phát ra cùng một âm mỗi lần. Đó là thứ người nghe nghe thấy;")
    _say("`(khớp cổng)` là chuyện của cổng neo tên và không phải câu hỏi ở đây.")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("surface", help="tên như nó viết trong sách, ví dụ Jake")
    parser.add_argument("candidates", nargs="*", help="các cách đọc muốn thử")
    parser.add_argument("--takes", type=int, default=10)
    parser.add_argument("--report", action="store_true", help="chỉ in kết quả đã có")
    args = parser.parse_args(argv)

    if args.report or not args.candidates:
        return report(args.surface)

    running = [
        path
        for path in Path("D:/Novels/Audiobooks/_versions").glob("*/*/project.sqlite3")
        if _alive(path.parent)
    ]
    if running:
        _say("CÓ LÔ ĐANG BAY - script này sinh audio thật và sẽ lấy GPU của nó:")
        for path in running[:3]:
            _say(f"   {path.parent.name}")
        _say("Đợi lô xong rồi chạy lại.")
        return 3

    LAB.mkdir(parents=True, exist_ok=True)
    for index, spoken in enumerate(args.candidates, 1):
        _say("")
        _say(f"--- {index}/{len(args.candidates)}: {args.surface} đọc là {spoken!r} ---")
        project = build_project(args.surface, spoken, args.takes, index)
        if project is None:
            continue
        run_project(project)
        forms = heard_forms(project, args.surface)
        total = sum(forms.values()) or 1
        _say(f"    {sum(forms.values())} lần neo, {len(forms)} dạng, đỉnh {max(forms.values())/total*100:.0f}%"
             if forms else "    không có neo nào - cách đọc trùng chữ viết?")
    _say("")
    return report(args.surface)


def _alive(project: Path) -> bool:
    try:
        conn = sqlite3.connect(f"file:{project / 'project.sqlite3'}?mode=ro", uri=True)
        try:
            beats = [
                time.time() - float(row[0] or 0.0)
                for row in conn.execute("SELECT heartbeat_at FROM worker_leases")
            ]
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    return bool(beats) and min(beats) < 180.0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
